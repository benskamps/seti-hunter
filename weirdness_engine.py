"""
SETI Weirdness & Anomaly Assessment Engine
==========================================
Evaluates radio astronomy filterbank (.fil) and HDF5 (.h5) spectrograms across
five orthogonal axes of 'weirdness', coupled with an ON-target vs OFF-target
sky-localization veto (one ON scan vs one OFF scan, not a full ABACAD cadence):

1. Narrowband De-Doppler Drift SNR (linear drifting carriers)
2. Temporal Kurtosis & Pulsed Duty-Cycle Anomaly (blinking beacons / fast bursts)
3. Non-Linear Ridge Curvature / Acceleration (chirps, curved orbits, frequency-hopping)
4. 2D Time-Frequency Morphological Structure (SVD low-rank structure / modulated sidebands)
5. Unsupervised Manifold Outlier Distance (Isolation Forest + PCA reconstruction error)
6. ON/OFF Sky-Localization Veto (ON-target power vs OFF-target reference power in the exact MHz window)
"""

import os
import math
import time
import json
import numpy as np
from scipy import stats, ndimage
from sklearn.ensemble import IsolationForest
from sklearn.decomposition import PCA
from sklearn.preprocessing import RobustScaler
import hdf5plugin  # noqa: F401 - required before h5py/blimpy reads bitshuffle HDF5
import h5py
from blimpy import Waterfall


def load_spectrogram_fast(filepath: str, max_chans_per_chunk: int = 1_048_576):
    """
    Loads a Breakthrough Listen .h5 or .fil spectrogram into memory efficiently.
    Returns:
        data: 2D float32 array of shape (n_time, n_freq) in ascending frequency order
        freqs: 1D float64 array of channel frequencies in MHz (ascending)
        header: dict of observation metadata
    """
    ext = os.path.splitext(filepath)[1].lower()
    if ext in (".h5", ".hdf5"):
        with h5py.File(filepath, "r") as f:
            dset = f["data"]
            attrs = dict(dset.attrs)
            shape = dset.shape  # (n_time, n_ifs, n_chans)
            raw = dset[:, 0, :].astype(np.float32)

            fch1 = float(attrs.get("fch1", 0.0))
            foff = float(attrs.get("foff", -1.0))
            tsamp = float(attrs.get("tsamp", 1.0))
            tstart = float(attrs.get("tstart", 0.0))
            source_name = attrs.get("source_name", b"UNKNOWN")
            if isinstance(source_name, bytes):
                source_name = source_name.decode("utf-8", errors="ignore")
            n_chans = shape[2]
            freqs = fch1 + np.arange(n_chans, dtype=np.float64) * foff
            header = {
                "source_name": str(source_name).strip(),
                "fch1_mhz": fch1,
                "foff_mhz": foff,
                "foff_hz": abs(foff) * 1e6,
                "tsamp_s": tsamp,
                "tstart_mjd": tstart,
                "n_time": shape[0],
                "n_chans": n_chans,
                "total_duration_s": shape[0] * tsamp,
                "bandwidth_mhz": abs(n_chans * foff),
            }
    else:
        wf = Waterfall(filepath, max_load=4.0)
        raw = wf.data[:, 0, :].astype(np.float32)
        attrs = wf.header
        fch1 = float(attrs.get("fch1", 0.0))
        foff = float(attrs.get("foff", -1.0))
        tsamp = float(attrs.get("tsamp", 1.0))
        tstart = float(attrs.get("tstart", 0.0))
        source_name = str(attrs.get("source_name", "UNKNOWN")).strip()
        n_chans = raw.shape[1]
        freqs = fch1 + np.arange(n_chans, dtype=np.float64) * foff
        header = {
            "source_name": source_name,
            "fch1_mhz": fch1,
            "foff_mhz": foff,
            "foff_hz": abs(foff) * 1e6,
            "tsamp_s": tsamp,
            "tstart_mjd": tstart,
            "n_time": raw.shape[0],
            "n_chans": n_chans,
            "total_duration_s": raw.shape[0] * tsamp,
            "bandwidth_mhz": abs(n_chans * foff),
        }

    # Ensure ascending frequency order for uniform indexing
    if freqs[0] > freqs[-1]:
        freqs = freqs[::-1].copy()
        raw = raw[:, ::-1].copy()

    return raw, freqs, header


def track_span_s(header: dict, n_time: int) -> float:
    """Time between the first and last spectra of a scan. A de-Doppler track with a total
    shift of s bins moves s bins over this span (n_time - 1 sample intervals)."""
    return max((n_time - 1) * header.get("tsamp_s", 18.25), 1.0)


def normalize_bandpass(data: np.ndarray, tile_width: int = 256) -> np.ndarray:
    """
    Removes coarse-channel polyphase filterbank (PFB) bandpass shape and DC spikes.
    Returns a standardized z-score spectrogram (n_time, n_chans) where background
    thermal noise has median ~0 and robust std ~1.
    """
    n_time, n_chans = data.shape
    # Trim to multiple of tile_width
    usable = (n_chans // tile_width) * tile_width
    trimmed = data[:, :usable]

    # Step 1: Remove slow bandpass ripple using median across time, smoothed over 64 channels
    time_median = np.median(trimmed, axis=0)
    # Mask extreme narrowband spikes in the bandpass template via median filter
    smooth_bp = ndimage.median_filter(time_median, size=33)
    smooth_bp = np.maximum(smooth_bp, 1e-12)
    flat = trimmed / smooth_bp[None, :] - 1.0

    # Step 2: Suppress periodic FFT coarse-channel DC spike bins
    # In GBT medium-res (.0002) files, coarse channels are typically 1024 or 512 bins wide
    for period in (512, 1024):
        if usable >= period * 4:
            folded = np.median(np.abs(flat).reshape(n_time, -1, period), axis=(0, 1))
            med_f = np.median(folded)
            mad_f = np.median(np.abs(folded - med_f)) + 1e-9
            dc_bins = np.where((folded - med_f) / (1.4826 * mad_f) > 8.0)[0]
            for b in dc_bins:
                flat[:, b::period] = 0.0

    # Step 3: Normalize each tile of `tile_width` channels by its local robust noise floor
    reshaped = flat.reshape(n_time, -1, tile_width)  # (T, N_tiles, W)
    tile_med = np.median(reshaped, axis=(0, 2), keepdims=True)
    tile_mad = np.median(np.abs(reshaped - tile_med), axis=(0, 2), keepdims=True)
    tile_std = np.maximum(1.4826 * tile_mad, 1e-7)
    z_tiles = (reshaped - tile_med) / tile_std
    return z_tiles.reshape(n_time, usable), usable


def compute_dedoppler_snr(
    z_tiles: np.ndarray, max_shift_bins: int = 12, calibrate: bool = True
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Vectorized De-Doppler shift-and-stack across all tiles simultaneously.
    Input:
        z_tiles: shape (T, N_tiles, W)
    Returns:
        best_snr: (N_tiles,) peak integrated SNR across all drift rates and channels
        best_drift_bins: (N_tiles,) total frequency bin shift from t=0 to t=T-1
        best_chan_in_tile: (N_tiles,) starting channel index inside tile

    calibrate=True measures SNR against the empirical spread of the other drift tracks in
    the same tile at the same drift rate (median and 1.4826*MAD over the tile's channels).
    calibrate=False is the old white-noise assumption, track sum / sqrt(T), which is 2-4x
    too optimistic when channels carry slow, channel-to-channel structure (TRAPPIST-1).
    """
    T, N_tiles, W = z_tiles.shape
    sqrt_T = math.sqrt(max(T, 1))

    best_snr = np.full(N_tiles, -1e9, dtype=np.float32)
    best_drift = np.zeros(N_tiles, dtype=np.int32)
    best_chan = np.zeros(N_tiles, dtype=np.int32)

    shifts = range(-max_shift_bins, max_shift_bins + 1)
    span = max(T - 1, 1)

    for total_shift in shifts:
        # Accumulate shifted time rows
        acc = np.zeros((N_tiles, W), dtype=np.float32)
        for t in range(T):
            # round(total_shift * t / span), halves rounded up, in exact integer arithmetic
            # (drift_aligned_snr rounds the same way, so both trace the same channels)
            s = (2 * total_shift * t + span) // (2 * span)
            row = z_tiles[t]
            if s == 0:
                acc += row
            elif s > 0:
                acc[:, :-s] += row[:, s:]
            else:
                acc[:, -s:] += row[:, :s]
        snr_profile = acc / sqrt_T
        # Avoid edge wrap artifacts
        pad = abs(total_shift) + 1
        edges = pad < W // 2
        if calibrate:
            interior = snr_profile[:, pad:-pad] if edges else snr_profile
            med = np.median(interior, axis=1, keepdims=True)
            mad = np.median(np.abs(interior - med), axis=1, keepdims=True)
            snr_profile = (snr_profile - med) / np.maximum(1.4826 * mad, 1e-6)
        if edges:
            snr_profile[:, :pad] = 0.0
            snr_profile[:, -pad:] = 0.0

        tile_max_chan = np.argmax(snr_profile, axis=1)
        tile_max_snr = snr_profile[np.arange(N_tiles), tile_max_chan]

        improved = tile_max_snr > best_snr
        best_snr[improved] = tile_max_snr[improved]
        best_drift[improved] = total_shift
        best_chan[improved] = tile_max_chan[improved]

    return best_snr, best_drift, best_chan


def extract_tile_features(z_tiles: np.ndarray, header: dict, tile_width: int = 256) -> dict:
    """
    Computes the 5 orthogonal weirdness metrics + 12-D feature matrix for every spectral tile.
    z_tiles: shape (T, N_tiles, W)
    """
    T, N_tiles, W = z_tiles.shape

    # 1. Classical & Drifting Narrowband Metric (Axis 1)
    drift_snr, drift_bins, best_chan = compute_dedoppler_snr(z_tiles, max_shift_bins=10)
    foff_hz = header.get("foff_hz", 2800.0)
    drift_rate_hz_s = (drift_bins * foff_hz) / track_span_s(header, T)

    # Zero-drift static SNR (pure vertical line indicator — often local oscillator RFI)
    static_snr = np.max(np.sum(z_tiles, axis=0) / math.sqrt(max(T, 1)), axis=1)

    # 2. Temporal Kurtosis & Burstiness (Axis 2: Pulsed / Transient Beacons)
    # Channel-wise temporal kurtosis inside each tile
    # Pick the highest-variance channel per tile and measure temporal spikiness
    chan_energy = np.mean(np.square(np.maximum(z_tiles, 0.0)), axis=0)  # (N_tiles, W)
    peak_chan_idx = np.argmax(chan_energy, axis=1)
    peak_time_series = z_tiles[:, np.arange(N_tiles), peak_chan_idx]  # (T, N_tiles)

    ts_max = np.max(peak_time_series, axis=0)
    ts_med = np.median(peak_time_series, axis=0)
    ts_std = np.std(peak_time_series, axis=0) + 1e-6
    kurtosis_raw = stats.kurtosis(peak_time_series, axis=0, fisher=True, nan_policy="omit")
    kurtosis_raw = np.nan_to_num(kurtosis_raw, nan=0.0, posinf=20.0, neginf=0.0)
    # Burstiness combines high peak SNR in a single time step with high temporal kurtosis
    burst_score = np.clip(kurtosis_raw, 0, 50) * np.log1p(np.maximum(ts_max - ts_med, 0.0))

    # 3. Non-Linear Ridge Curvature / Chirp / Frequency-Hopping (Axis 3)
    # At each time step t, find the peak frequency bin and its SNR
    t_peak_bins = np.argmax(z_tiles, axis=2).astype(np.float32)  # (T, N_tiles)
    t_peak_vals = np.max(z_tiles, axis=2)  # (T, N_tiles)
    mean_ridge_snr = np.mean(t_peak_vals, axis=0)

    # Fit linear trend f(t) = a*t + b weighted by SNR, measure non-linear curvature & jumpiness
    t_norm = np.linspace(-1.0, 1.0, T, dtype=np.float32)[:, None]
    weights = np.maximum(t_peak_vals - 2.0, 0.01)
    w_sum = np.sum(weights, axis=0) + 1e-6
    t_mean = np.sum(weights * t_norm, axis=0) / w_sum
    f_mean = np.sum(weights * t_peak_bins, axis=0) / w_sum
    cov_tf = np.sum(weights * (t_norm - t_mean) * (t_peak_bins - f_mean), axis=0) / w_sum
    var_t = np.sum(weights * np.square(t_norm - t_mean), axis=0) / w_sum + 1e-6
    slope = cov_tf / var_t
    linear_fit = f_mean[None, :] + slope[None, :] * (t_norm - t_mean[None, :])
    residual = np.abs(t_peak_bins - linear_fit)
    weighted_resid = np.sum(weights * residual, axis=0) / w_sum

    # Count how many time steps have a strong localized peak (> 4.5 sigma) that moves non-linearly
    active_steps = np.mean((t_peak_vals > 4.5).astype(np.float32), axis=0)
    # Curvature score rewards high active steps where ridge moves smoothly or hops (1.5 < resid < 25 bins)
    curvature_factor = np.exp(-np.square((weighted_resid - 5.0) / 8.0))
    ridge_curvature_score = mean_ridge_snr * active_steps * (1.0 + 3.0 * curvature_factor)

    # 4. 2D Morphological Structure & Spectral Entropy (Axis 4)
    # Positive excess power distribution
    pos_power = np.maximum(z_tiles, 0.0) ** 2 + 1e-9
    total_tile_power = np.sum(pos_power, axis=(0, 2))
    p_norm = pos_power / total_tile_power[None, :, None]
    shannon_entropy = -np.sum(p_norm * np.log(p_norm), axis=(0, 2))
    max_entropy = math.log(T * W)
    # Negentropy (concentration of structure in time-frequency plane)
    concentration = np.clip(1.0 - (shannon_entropy / max_entropy), 0.0, 1.0)

    # Multi-peak comb / sideband detector: count distinct frequency channels with integrated SNR > 5
    chan_int_snr = np.sum(z_tiles, axis=0) / math.sqrt(max(T, 1))  # (N_tiles, W)
    active_chans_count = np.sum((chan_int_snr > 5.0).astype(np.float32), axis=1)
    # Sweet spot for structured narrowband/sideband complexes is 2 to 18 channels out of 256
    comb_bonus = np.where((active_chans_count >= 2) & (active_chans_count <= 20), np.sqrt(active_chans_count), 1.0)
    morphology_score = concentration * np.log1p(np.maximum(drift_snr, ts_max)) * comb_bonus * 10.0

    # 5. Unsupervised Manifold Outlier Score (Axis 5: Isolation Forest + PCA Reconstruction Error)
    # Build 10-D feature vector per tile
    q99 = np.percentile(z_tiles, 99.5, axis=(0, 2))
    q95 = np.percentile(z_tiles, 95.0, axis=(0, 2))
    temporal_diff = np.mean(np.abs(np.diff(z_tiles, axis=0)), axis=(0, 2))
    spectral_diff = np.mean(np.abs(np.diff(z_tiles, axis=2)), axis=(0, 2))

    feat_matrix = np.column_stack([
        drift_snr,
        static_snr,
        np.abs(drift_bins),
        burst_score,
        ridge_curvature_score,
        morphology_score,
        active_chans_count,
        q99,
        q95,
        temporal_diff / (spectral_diff + 1e-6),
    ])
    feat_matrix = np.nan_to_num(feat_matrix, nan=0.0, posinf=100.0, neginf=-100.0)

    scaler = RobustScaler()
    X_scaled = scaler.fit_transform(feat_matrix)
    X_scaled = np.clip(X_scaled, -50.0, 50.0)

    # PCA Reconstruction Error (captures unusual combinations of features)
    n_comp = min(4, X_scaled.shape[1], max(1, N_tiles // 10))
    pca = PCA(n_components=n_comp, random_state=42)
    X_proj = pca.fit_transform(X_scaled)
    X_recon = pca.inverse_transform(X_proj)
    pca_recon_err = np.sqrt(np.mean(np.square(X_scaled - X_recon), axis=1))

    # Isolation Forest Anomaly Score
    iso = IsolationForest(n_estimators=100, contamination=0.01, random_state=42, n_jobs=-1)
    iso.fit(X_scaled)
    iso_score = -iso.score_samples(X_scaled)  # Higher = more anomalous

    manifold_score = pca_recon_err * iso_score

    return {
        "drift_snr": drift_snr,
        "static_snr": static_snr,
        "drift_bins": drift_bins,
        "drift_rate_hz_s": drift_rate_hz_s,
        "best_chan": best_chan,
        "burst_score": burst_score,
        "kurtosis": kurtosis_raw,
        "ts_max": ts_max,
        "ridge_curvature_score": ridge_curvature_score,
        "weighted_resid": weighted_resid,
        "morphology_score": morphology_score,
        "active_chans_count": active_chans_count,
        "manifold_score": manifold_score,
        "pca_recon_err": pca_recon_err,
        "iso_score": iso_score,
    }


def standardize_metric(arr: np.ndarray) -> np.ndarray:
    """Converts a raw metric vector into positive robust sigma units above median."""
    med = np.median(arr)
    mad = np.median(np.abs(arr - med))
    scale = max(1.4826 * mad, float(np.std(arr)) * 0.5, 1e-6)
    return np.clip((arr - med) / scale, 0.0, 100.0)


def classify_anomaly_type(row: dict) -> str:
    """Assigns a human-readable morphological taxonomy label to a detected anomaly."""
    if row["off_peak_snr"] > OFF_DETECTION_SNR:
        return "Terrestrial / Satellite RFI (Present in OFF)"
    if abs(row["drift_bins"]) >= 2 and row["drift_snr"] > row["static_snr"] * 1.05:
        return f"Drifting Narrowband Technosignature Candidate ({row['drift_rate_hz_s']:+.2f} Hz/s)"
    if row["z_burst"] > row["z_drift"] and row["kurtosis"] > 4.0:
        return "Pulsed / Transient Narrowband Burst"
    if row["z_curvature"] > row["z_drift"] and row["weighted_resid"] > 1.8:
        return "Non-Linear Chirp / Accelerated Ridge"
    if row["active_chans_count"] >= 3 and row["z_morphology"] > 5.0:
        return "Structured Multi-Carrier / Sideband Complex"
    return "Narrowband Sky-Localized Anomaly"


OFF_DETECTION_SNR = 8.0


def onoff_veto_multiplier(off_peak_snr: np.ndarray, on_off_ratio: np.ndarray) -> np.ndarray:
    """
    Anything detected in the OFF scan is not sky-localized, however much louder it is
    in ON (RFI strength changes between scans), so it gets the strong 0.15 suppression.
    Only tiles quiet in OFF earn the sqrt(ON/OFF) boost.
    """
    return np.where(
        off_peak_snr > OFF_DETECTION_SNR,
        0.15,
        np.clip(np.sqrt(on_off_ratio), 0.5, 4.0),
    )


def assess_cadence(
    on_filepath: str,
    off_filepath: str | None = None,
    tile_width: int = 256,
    top_k: int = 8,
) -> dict:
    """
    Runs the full 5-axis SETI Weirdness Assessment on an ON-target file and
    performs an ON/OFF sky-localization veto against a single OFF-target file.
    """
    on = load_spectrogram_fast(on_filepath)
    off = load_spectrogram_fast(off_filepath) if (off_filepath and os.path.exists(off_filepath)) else None
    summary = assess_arrays(on, off, tile_width=tile_width, top_k=top_k)
    summary["on_file"] = os.path.basename(on_filepath)
    summary["off_file"] = os.path.basename(off_filepath) if off_filepath else None
    return summary


def assess_arrays(
    on: tuple[np.ndarray, np.ndarray, dict],
    off: tuple[np.ndarray, np.ndarray, dict] | None = None,
    tile_width: int = 256,
    top_k: int = 8,
) -> dict:
    """assess_cadence on already-loaded (data, freqs, header) tuples, as returned by
    load_spectrogram_fast. Also returns a negative control: the strongest carrier in
    the OFF scan, which any working cadence check must call RFI."""
    t0 = time.time()
    on_raw, on_freqs, on_hdr = on
    on_z, usable_chans = normalize_bandpass(on_raw, tile_width=tile_width)
    on_freqs = on_freqs[:usable_chans]

    T, _ = on_z.shape
    N_tiles = usable_chans // tile_width
    on_tiles = on_z.reshape(T, N_tiles, tile_width)

    feats = extract_tile_features(on_tiles, on_hdr, tile_width=tile_width)

    # Normalize the OFF-target scan if provided
    off_tiles = None
    if off is not None:
        off_raw, off_freqs, off_hdr = off
        off_z, off_usable = normalize_bandpass(off_raw, tile_width=tile_width)
        common_tiles = min(N_tiles, off_usable // tile_width)
        off_tiles = off_z[:, : common_tiles * tile_width].reshape(off_z.shape[0], common_tiles, tile_width)

    # Compute OFF-target activity at every corresponding frequency tile
    off_peak_snr = np.ones(N_tiles, dtype=np.float32) * 2.5
    negative_control = None
    if off_tiles is not None:
        T_off = off_tiles.shape[0]
        c_tiles = off_tiles.shape[1]
        off_drift_snr, off_drift_bins, off_best_chan = compute_dedoppler_snr(off_tiles, max_shift_bins=6)
        off_max_point = np.max(off_tiles, axis=(0, 2)) / 2.0
        off_peak_snr[:c_tiles] = np.maximum(off_drift_snr, off_max_point)
        k = int(np.argmax(off_drift_snr))
        negative_control = {
            "label": "control: strongest OFF_1 carrier",
            "tile_idx": k,
            "peak_freq_mhz": float(off_freqs[k * tile_width + int(off_best_chan[k])]),
            "drift_rate_hz_s": float(off_drift_bins[k]) * off_hdr["foff_hz"] / track_span_s(off_hdr, T_off),
            "t_ref_mjd": off_hdr["tstart_mjd"],
            "off_drift_snr": round(float(off_drift_snr[k]), 2),
        }

    # ON vs OFF Exclusivity Ratio (higher means signal ONLY exists when pointing at the star)
    on_effective_snr = np.maximum(feats["drift_snr"], feats["ts_max"] * 0.7)
    on_off_ratio = (on_effective_snr + 1.0) / ( np.maximum(off_peak_snr, 2.5) + 1.0 )

    # Standardize each of the 5 weirdness axes into robust sigma units
    z_drift = standardize_metric(feats["drift_snr"])
    z_burst = standardize_metric(feats["burst_score"])
    z_curvature = standardize_metric(feats["ridge_curvature_score"])
    z_morphology = standardize_metric(feats["morphology_score"])
    z_manifold = standardize_metric(feats["manifold_score"])

    # Boost genuinely drifting signals (non-zero Doppler drift) since geostationary satellites have 0 drift
    doppler_motion_bonus = np.where(np.abs(feats["drift_bins"]) >= 1, 1.35, 1.0)

    # Intrinsic Weirdness Score (combines all 5 axes)
    intrinsic_weirdness = (
        0.30 * z_drift * doppler_motion_bonus
        + 0.20 * z_burst
        + 0.20 * z_curvature
        + 0.15 * z_morphology
        + 0.15 * z_manifold
    )

    # Sky-Localized Weirdness Score (penalizes tiles with signal in the OFF-target scan)
    abacad_veto_multiplier = onoff_veto_multiplier(off_peak_snr, on_off_ratio)

    total_weirdness_score = intrinsic_weirdness * abacad_veto_multiplier

    # Ignore coarse-channel boundary edges or completely dead tiles
    valid_mask = (feats["drift_snr"] > 4.5) | (feats["ts_max"] > 6.0)
    scored = np.where(valid_mask, total_weirdness_score, -1.0)

    # Select top_k Sky-Localized Anomalies AND top_k interesting RFI examples for comparison
    order = np.argsort(scored)[::-1]
    candidates = []
    used_tiles = set()

    for idx in order:
        if len(candidates) >= top_k:
            break
        if scored[idx] <= 0:
            break
        # Prevent picking immediately adjacent tiles of a wideband interferer
        if any(abs(int(idx) - u) <= 2 for u in used_tiles):
            continue
        used_tiles.add(int(idx))

        c_start = int(idx) * tile_width
        c_end = c_start + tile_width
        tile_freqs = on_freqs[c_start:c_end]
        center_freq_mhz = float(np.mean(tile_freqs))
        peak_freq_mhz = float(tile_freqs[feats["best_chan"][idx]])

        on_cutout = on_tiles[:, idx, :].copy()
        off_cutout = (
            off_tiles[:, idx, :].copy()
            if (off_tiles is not None and idx < off_tiles.shape[1])
            else np.zeros_like(on_cutout)
        )

        row = {
            "tile_idx": int(idx),
            "center_freq_mhz": round(center_freq_mhz, 6),
            "peak_freq_mhz": round(peak_freq_mhz, 6),
            "freq_span_khz": round(abs(tile_freqs[-1] - tile_freqs[0]) * 1e3, 2),
            "total_weirdness_score": round(float(total_weirdness_score[idx]), 2),
            "intrinsic_weirdness": round(float(intrinsic_weirdness[idx]), 2),
            "drift_snr": round(float(feats["drift_snr"][idx]), 2),
            "static_snr": round(float(feats["static_snr"][idx]), 2),
            "drift_bins": int(feats["drift_bins"][idx]),
            "drift_rate_hz_s": round(float(feats["drift_rate_hz_s"][idx]), 3),
            "t_ref_mjd": on_hdr["tstart_mjd"],
            "burst_score": round(float(feats["burst_score"][idx]), 2),
            "kurtosis": round(float(feats["kurtosis"][idx]), 2),
            "ts_max": round(float(feats["ts_max"][idx]), 2),
            "ridge_curvature_score": round(float(feats["ridge_curvature_score"][idx]), 2),
            "weighted_resid": round(float(feats["weighted_resid"][idx]), 2),
            "morphology_score": round(float(feats["morphology_score"][idx]), 2),
            "active_chans_count": int(feats["active_chans_count"][idx]),
            "manifold_score": round(float(feats["manifold_score"][idx]), 2),
            "off_peak_snr": round(float(off_peak_snr[idx]), 2),
            "on_off_ratio": round(float(on_off_ratio[idx]), 2),
            "z_drift": round(float(z_drift[idx]), 2),
            "z_burst": round(float(z_burst[idx]), 2),
            "z_curvature": round(float(z_curvature[idx]), 2),
            "z_morphology": round(float(z_morphology[idx]), 2),
            "z_manifold": round(float(z_manifold[idx]), 2),
            "on_cutout": on_cutout,
            "off_cutout": off_cutout,
            "tile_freqs_mhz": tile_freqs,
        }
        row["classification"] = classify_anomaly_type(row)
        candidates.append(row)

    elapsed = time.time() - t0
    summary = {
        "source_name": on_hdr["source_name"],
        "header": on_hdr,
        "n_tiles_evaluated": int(N_tiles),
        "n_channels_evaluated": int(usable_chans),
        "elapsed_s": round(elapsed, 2),
        "throughput_mchans_s": round((usable_chans * T) / max(elapsed * 1e6, 1e-6), 2),
        "max_weirdness_score": round(float(np.max(total_weirdness_score)), 2),
        "median_weirdness_score": round(float(np.median(total_weirdness_score)), 2),
        "rfi_vetoed_tiles": int(np.sum(off_peak_snr > OFF_DETECTION_SNR)),
        "sky_localized_tiles_gt_15": int(np.sum((total_weirdness_score > 15.0) & (off_peak_snr <= OFF_DETECTION_SNR))),
        "candidates": candidates,
        "negative_control": negative_control,
    }
    return summary


def run_synthetic_verification_benchmark() -> dict:
    """
    Self-verification test: Generates realistic radio telescope thermal noise + PFB bandpass
    (16 time steps x 65,536 channels = 256 tiles of 256 channels) for an ON/OFF pair,
    injects 5 known ground-truth signals:
      1. Tile 42 (ON only): Linear Doppler-drifting narrowband carrier (+4 bins drift, SNR ~ 18)
      2. Tile 95 (ON only): Parabolic accelerating chirp (curved trajectory, SNR ~ 16)
      3. Tile 140 (ON only): Pulsed narrowband beacon (active in 3 of 16 time steps, SNR ~ 22)
      4. Tile 190 (ON only): Modulated 5-carrier frequency comb (sideband structure)
      5. Tile 210 (ON + OFF): Strong terrestrial satellite RFI (SNR ~ 35 in both ON and OFF)
    Verifies that all 4 ON-only weird signals rank in the top 5 candidates and that
    Tile 210 (ON+OFF RFI) is properly suppressed by the ABACAD veto.
    """
    rng = np.random.default_rng(20261015)
    T, N_chans, W = 16, 65536, 256
    N_tiles = N_chans // W

    on_data = rng.normal(loc=100.0, scale=1.0, size=(T, N_chans)).astype(np.float32)
    off_data = rng.normal(loc=100.0, scale=1.0, size=(T, N_chans)).astype(np.float32)

    # 1. Tile 42: Linear Doppler-drifting narrowband carrier (ON only)
    for t in range(T):
        c = 42 * W + 120 + int(round(5.0 * t / (T - 1)))
        on_data[t, c] += 7.5

    # 2. Tile 95: Parabolic accelerating chirp (ON only)
    for t in range(T):
        norm_t = (t - T / 2) / (T / 2)
        c = 95 * W + 100 + int(round(14.0 * (norm_t ** 2)))
        on_data[t, c : c + 2] += 6.5

    # 3. Tile 140: Pulsed narrowband beacon (ON only, bursts at t=3, 8, 13)
    for t in (3, 8, 13):
        on_data[t, 140 * W + 80] += 18.0

    # 4. Tile 190: Modulated 5-carrier frequency comb (ON only)
    for k in range(5):
        c = 190 * W + 60 + k * 12
        on_data[:, c] += 4.8

    # 5. Tile 210: Terrestrial RFI present in BOTH ON and OFF
    on_data[:, 210 * W + 128] += 14.0
    off_data[:, 210 * W + 128] += 14.5

    # 6. Tile 230: RFI clearly present in OFF but ~3x louder in ON (e.g. a sidelobe
    #    pickup that changed between scans). Still not sky-localized, so it must be vetoed.
    on_data[:, 230 * W + 64] += 40.0
    off_data[:, 230 * W + 64] += 14.0

    hdr = {
        "source_name": "SYNTHETIC_BENCHMARK",
        "fch1_mhz": 1420.0,
        "foff_mhz": 0.0028,
        "foff_hz": 2800.0,
        "tsamp_s": 18.25,
        "total_duration_s": 16 * 18.25,
    }

    on_z, _ = normalize_bandpass(on_data, tile_width=W)
    off_z, _ = normalize_bandpass(off_data, tile_width=W)
    on_tiles = on_z.reshape(T, N_tiles, W)
    off_tiles = off_z.reshape(T, N_tiles, W)

    feats = extract_tile_features(on_tiles, hdr, tile_width=W)
    off_drift_snr, _, _ = compute_dedoppler_snr(off_tiles, max_shift_bins=6)
    off_max_point = np.max(off_tiles, axis=(0, 2)) / 2.0
    off_peak_snr = np.maximum(off_drift_snr, off_max_point)

    on_effective_snr = np.maximum(feats["drift_snr"], feats["ts_max"] * 0.7)
    on_off_ratio = (on_effective_snr + 1.0) / (np.maximum(off_peak_snr, 2.5) + 1.0)

    z_drift = standardize_metric(feats["drift_snr"])
    z_burst = standardize_metric(feats["burst_score"])
    z_curvature = standardize_metric(feats["ridge_curvature_score"])
    z_morphology = standardize_metric(feats["morphology_score"])
    z_manifold = standardize_metric(feats["manifold_score"])
    doppler_motion_bonus = np.where(np.abs(feats["drift_bins"]) >= 1, 1.35, 1.0)

    intrinsic_weirdness = (
        0.30 * z_drift * doppler_motion_bonus
        + 0.20 * z_burst
        + 0.20 * z_curvature
        + 0.15 * z_morphology
        + 0.15 * z_manifold
    )
    abacad_veto_multiplier = onoff_veto_multiplier(off_peak_snr, on_off_ratio)
    total_weirdness_score = intrinsic_weirdness * abacad_veto_multiplier

    top_tiles = [int(x) for x in np.argsort(total_weirdness_score)[::-1][:6]]
    expected_on_tiles = {42, 95, 140, 190}
    recovered = expected_on_tiles.intersection(set(top_tiles[:5]))
    rfi_vetoed = 210 not in top_tiles[:4]
    loud_on_rfi_vetoed = 230 not in top_tiles[:4]

    return {
        "passed": (len(recovered) == 4) and rfi_vetoed and loud_on_rfi_vetoed,
        "top_6_tiles": top_tiles,
        "recovered_on_targets": sorted(list(recovered)),
        "rfi_tile_210_score": round(float(total_weirdness_score[210]), 2),
        "rfi_tile_210_intrinsic": round(float(intrinsic_weirdness[210]), 2),
        "rfi_tile_230_score": round(float(total_weirdness_score[230]), 2),
        "rfi_tile_230_intrinsic": round(float(intrinsic_weirdness[230]), 2),
        "scores_by_injected_tile": {
            t: round(float(total_weirdness_score[t]), 2) for t in [42, 95, 140, 190, 210, 230]
        },
    }


def run_noise_calibration_benchmark(calibrate: bool = True) -> dict:
    """
    Self-test of the de-Doppler SNR calibration. Two signal-free scans (16 x 65,536 channels):
    white noise, and white noise plus a constant per-channel offset (sigma 0.6) that the
    33-channel bandpass median filter cannot remove, which is what TRAPPIST-1's scans look
    like (nearby-track spread 2-4x the white-noise value). In both, fewer than 0.5% of tiles
    may exceed the OFF_DETECTION_SNR "present" bar. A carrier injected into the structured
    scan (tile 77, +4 bins drift) must still be the top tile at SNR >= 10.
    calibrate=False (the old white-noise SNR) must FAIL the structured-noise case.
    """
    rng = np.random.default_rng(20261017)
    T, N, W = 16, 65536, 256
    white = rng.normal(100.0, 1.0, size=(T, N)).astype(np.float32)
    structured = white + rng.normal(0.0, 0.6, size=N).astype(np.float32)[None, :]
    with_signal = structured.copy()
    for t in range(T):
        with_signal[t, 77 * W + 100 + int(round(4.0 * t / (T - 1)))] += 8.0

    def best_snr(data):
        z, _ = normalize_bandpass(data, tile_width=W)
        snr, _, _ = compute_dedoppler_snr(z.reshape(T, N // W, W), max_shift_bins=10, calibrate=calibrate)
        return snr

    white_snr, struct_snr, sig_snr = best_snr(white), best_snr(structured), best_snr(with_signal)
    fa_white = float(np.mean(white_snr > OFF_DETECTION_SNR))
    fa_struct = float(np.mean(struct_snr > OFF_DETECTION_SNR))
    top = int(np.argmax(sig_snr))
    return {
        "passed": fa_white < 0.005 and fa_struct < 0.005 and top == 77 and float(sig_snr[77]) >= 10.0,
        "calibrate": calibrate,
        "white_false_alarm_frac": round(fa_white, 4),
        "structured_false_alarm_frac": round(fa_struct, 4),
        "white_median_best_snr": round(float(np.median(white_snr)), 2),
        "structured_median_best_snr": round(float(np.median(struct_snr)), 2),
        "injected_tile_77_snr": round(float(sig_snr[77]), 2),
        "top_tile_with_signal": top,
    }


# ---------------------------------------------------------------------------
# Full-cadence test (ON/OFF/ON/OFF[/ON/OFF]) for Stage 1 candidates
# ---------------------------------------------------------------------------
CADENCE_PRESENT_SNR = OFF_DETECTION_SNR  # same "present" bar as the Stage 1 OFF veto
CADENCE_SEARCH_BASE = 2                  # +/- channels searched around the predicted track
CADENCE_SEARCH_MAX = 40
CADENCE_BG_CHANS = 400                   # offsets beyond the search window used for the noise floor
SNR_AGREEMENT_TOL = 0.1                  # cadence vs Stage 1 SNR in the scan Stage 1 scored
CADENCE_VERDICTS = ("PASSES", "ONE-OFF", "PARTIAL", "RFI", "INCOMPLETE", "NOT-RECOVERED", "UNTESTED")


def cadence_search_chans(dt_s: float, ref_span: float) -> int:
    """Stage 1 quantizes drift to whole bins per track span of its own scan (ref_span), so
    the predicted position drifts off by <= 1/2 channel per ref_span of elapsed time (1 if
    Stage 1 picked a neighboring bin). The window allows that and no more: a wider one lets
    an unrelated nearby carrier stand in for the candidate (Codex review, bug 2)."""
    return int(min(CADENCE_SEARCH_MAX, CADENCE_SEARCH_BASE + math.ceil(abs(dt_s) / ref_span)))


def drift_aligned_snr(
    z: np.ndarray,
    freqs: np.ndarray,
    hdr: dict,
    sig: dict,
    search_chans: int,
    method: str = "dedoppler",
    noise: str = "tile",
    tile_width: int = 256,
) -> dict | None:
    """
    Measures a signal in one scan of a cadence. z is the normalize_bandpass() spectrogram
    (n_time, n_chans) with ascending freqs. sig has peak_freq_mhz at time t_ref_mjd and a
    drift_rate_hz_s. For every channel offset within +/-(search + background) of the
    predicted track, the scan is summed ALONG the drift track (de-Doppler), so a drifting
    signal keeps its full SNR. The SNR is the best offset in the search window against the
    robust spread (median, 1.4826*MAD) of the noise tracks. Returns None if the track
    leaves the band.

    noise="tile" (default) takes the noise tracks exactly as Stage 1's compute_dedoppler_snr
    does: every track with the same drift starting in the tile that holds the predicted start
    channel, minus |shift|+1 edge channels on each side. In the scan Stage 1 scored, both
    SNRs then agree. noise="local" is the earlier window (offsets beyond the search window
    out to +/-400 channels), kept for regression tests.

    method="timemean" reproduces the 2026-10-16 cadence_check.py measurement (a time-mean
    spectrum, +/-40 channels around the track's mid-scan position) for regression tests.
    """
    T, N = z.shape
    df_mhz = float(freqs[1] - freqs[0])
    t_rows = (hdr["tstart_mjd"] - sig["t_ref_mjd"]) * 86400.0 + np.arange(T) * hdr["tsamp_s"]
    if method == "timemean":
        t_rows = np.full(T, t_rows.mean())
        search_chans = CADENCE_SEARCH_MAX
    # Start channel at t_ref, then the drift in channels rounded half-up like Stage 1. The 1e-3
    # bias keeps exact halves rounding up despite the rounding of the stored drift rate;
    # non-half values sit at least 1/(2*(T-1)) channel from a boundary.
    c_ref = int(np.rint((sig["peak_freq_mhz"] - freqs[0]) / df_mhz))
    drift_ch = sig["drift_rate_hz_s"] * t_rows / (df_mhz * 1e6)
    c_rows = c_ref + np.floor(drift_ch + 0.5 + 1e-3).astype(np.int64)

    half = search_chans + 8 + CADENCE_BG_CHANS
    offs = np.arange(-half, half + 1)
    idx = c_rows[:, None] + offs[None, :]
    inside = (idx >= 0) & (idx < N)
    vals = np.where(inside, z[np.arange(T)[:, None], np.clip(idx, 0, N - 1)], 0.0)
    n_in = inside.sum(axis=0)
    dd = vals.sum(axis=0) / np.sqrt(np.maximum(n_in, 1))
    # Search only offsets whose whole track is in the band; unmeasured only if the
    # predicted track itself leaves it (a carrier near the band edge is still measured).
    win = (np.abs(offs) <= search_chans) & (n_in == T)
    if n_in[half] < T:
        return None

    if noise == "tile":
        start = c_rows[0] + offs  # start channel of each offset's track
        tile0 = (int(c_rows[0]) // tile_width) * tile_width
        pad = abs(int(c_rows[-1] - c_rows[0])) + 1
        lo, hi = (tile0 + pad, tile0 + tile_width - pad) if pad < tile_width // 2 else (tile0, tile0 + tile_width)
        bg = dd[(start >= lo) & (start < hi) & (n_in == T)]
    else:
        bg = dd[(np.abs(offs) > search_chans + 8) & (n_in == T)]
    if bg.size < 16:
        return None
    med = float(np.median(bg))
    sigma = max(1.4826 * float(np.median(np.abs(bg - med))), 1e-6)
    k = int(np.argmax(np.where(win, dd, -np.inf)))
    # raw_snr is the white-noise value (track sum / sqrt(T)). snr uses the measured spread of
    # nearby tracks, which on some scans (TRAPPIST-1) is 2-4x wider.
    return {"snr": (float(dd[k]) - med) / sigma, "raw_snr": float(dd[k]), "offset_ch": int(offs[k]),
            "search_chans": int(search_chans)}


def cadence_verdict(scans: list[dict]) -> tuple[str, str]:
    """
    scans: per-scan rows in observing order with "role" (ON/OFF) and "present" (bool, or
    None if the track left the band). Returns (verdict, detail):
      RFI           - present in any OFF scan
      PASSES        - present in every ON scan and no OFF scan
      ONE-OFF       - present only in the first ON scan (the one Stage 1 scored)
      NOT-RECOVERED - absent even from the first ON scan: the check could not see the
                      Stage 1 signal, so it says nothing about the candidate
      PARTIAL       - in some ON scans but not all
      INCOMPLETE    - no OFF hit, but at least one scan could not be measured, so the
                      cadence cannot be completed (never PASSES)
      UNTESTED      - the cadence has no OFF scan
    """
    on = [s["present"] for s in scans if s["role"] == "ON"]
    off = [s["present"] for s in scans if s["role"] == "OFF"]
    detail = f"in {sum(p is True for p in on)}/{len(on)} ON, {sum(p is True for p in off)}/{len(off)} OFF"
    n_unmeasured = sum(p is None for p in on + off)
    if n_unmeasured:
        detail += f", {n_unmeasured} scan(s) unmeasured"
    if not off:
        return "UNTESTED", detail + " (no OFF scan in this cadence)"
    if any(p is True for p in off):
        return "RFI", detail
    if n_unmeasured:
        return "INCOMPLETE", detail
    if all(on):
        return "PASSES", detail
    if not on[0]:
        return ("NOT-RECOVERED" if not any(on[1:]) else "PARTIAL"), detail
    if not any(on[1:]):
        return "ONE-OFF", detail
    return "PARTIAL", detail


def cadence_test_signals(
    scan_loader,
    roles: list[str],
    signals: list[dict],
    method: str = "dedoppler",
    tile_width: int = 256,
    noise: str = "tile",
) -> list[dict]:
    """
    Runs drift_aligned_snr for every signal in every scan. scan_loader(i) returns the
    (data, freqs, header) tuple of scan i; scans are loaded one at a time to bound memory.
    Each signal needs peak_freq_mhz, drift_rate_hz_s and t_ref_mjd, and gets back
    "cadence_scans", "cadence_verdict" and "cadence_detail".
    """
    rows = [[] for _ in signals]
    for i, role in enumerate(roles):
        data, freqs, hdr = scan_loader(i)
        z, usable = normalize_bandpass(data, tile_width=tile_width)
        del data
        freqs = freqs[:usable]
        span = track_span_s(hdr, z.shape[0])
        for j, sig in enumerate(signals):
            dt = (hdr["tstart_mjd"] - sig["t_ref_mjd"]) * 86400.0 + 0.5 * span
            # error bound at this scan's last row, in units of the reference scan's track span
            dt_last = dt + 0.5 * span
            search = cadence_search_chans(dt_last, sig.get("ref_span_s", span))
            m = drift_aligned_snr(z, freqs, hdr, sig, search, method=method, noise=noise, tile_width=tile_width)
            rows[j].append({
                "scan": i, "role": role, "dt_s": round(dt, 1),
                "snr": None if m is None else round(m["snr"], 2),
                "raw_snr": None if m is None else round(m["raw_snr"], 1),
                "offset_ch": None if m is None else m["offset_ch"],
                "search_chans": None if m is None else m["search_chans"],
                "present": None if m is None else bool(m["snr"] >= CADENCE_PRESENT_SNR),
            })
        del z
    out = []
    for sig, r in zip(signals, rows):
        verdict, detail = cadence_verdict(r)
        out.append({**sig, "cadence_scans": r, "cadence_verdict": verdict, "cadence_detail": detail})
    return out


def run_synthetic_cadence_benchmark(
    method: str = "dedoppler", scans_used: int | None = None, noise: str = "tile"
) -> dict:
    """
    Self-test of the full-cadence check, end to end: synthesizes a 6-scan ON/OFF/ON/OFF/ON/OFF
    cadence (16 x 65,536 channels per scan), runs Stage 1 (assess_arrays) on ON_1 vs OFF_1,
    then the cadence check on every Stage 1 candidate. Injected signals:
      tile  40  drifting carrier in all 3 ON scans               -> PASSES
      tile  90  drifting carrier in ON_1 only                     -> ONE-OFF
      tile 115  weak fast drifter in all 3 ON (smeared ~1.3 sigma
                per channel in a time-mean spectrum)              -> PASSES
      tile 140  carrier in ON_1 and ON_2, not ON_3                -> PARTIAL
      tile 230  carrier in ON_1 and OFF_2 only (Stage 1 sees no
                OFF power and calls it sky-localized)             -> RFI
      tile 190  zero-drift carrier in all 6 scans; the strongest
                OFF_1 carrier, so it is the negative control      -> RFI
    All five ON_1 signals must be Stage 1 candidates and every verdict must match. In ON_1,
    the scan Stage 1 scored, the cadence SNR of every Stage 1 candidate must equal Stage 1's
    drift_snr within SNR_AGREEMENT_TOL.
    method="timemean" (the old measurement), scans_used=2 (score the first ON/OFF pair
    only, i.e. no cadence check) or noise="local" (the old +/-400-channel noise window)
    must make this benchmark FAIL.
    """
    rng = np.random.default_rng(20261016)
    T, N, W = 16, 65536, 256
    tsamp, slew = 18.25, 30.0
    span = (T - 1) * tsamp
    roles = ["ON", "OFF", "ON", "OFF", "ON", "OFF"]
    t0_mjd = 60000.0
    tstarts = [t0_mjd + k * (T * tsamp + slew) / 86400.0 for k in range(6)]
    freqs = 1420.0 + np.arange(N, dtype=np.float64) * 0.0028

    # (tile, chan in tile at ON_1 t=0, channels drifted per scan span, amplitude, scans present, expected)
    injections = [
        (40, 100, 6.4, 4.0, {0, 2, 4}, "PASSES"),
        (90, 120, -3.3, 4.5, {0}, "ONE-OFF"),
        (115, 60, 9.6, 3.2, {0, 2, 4}, "PASSES"),
        (140, 140, 2.6, 4.0, {0, 2}, "PARTIAL"),
        (230, 80, -5.2, 4.2, {0, 3}, "RFI"),
        (190, 128, 0.0, 3.0, {0, 1, 2, 3, 4, 5}, "RFI"),
    ]
    scans = []
    for k in range(6):
        data = rng.normal(loc=100.0, scale=1.0, size=(T, N)).astype(np.float32)
        for tile, c_in, drift, amp, present, _ in injections:
            if k not in present:
                continue
            for t in range(T):
                elapsed = (tstarts[k] - t0_mjd) * 86400.0 + t * tsamp
                data[t, int(round(tile * W + c_in + drift * elapsed / span))] += amp
        hdr = {
            "source_name": "SYNTHETIC_CADENCE", "fch1_mhz": float(freqs[0]), "foff_mhz": 0.0028,
            "foff_hz": 2800.0, "tsamp_s": tsamp, "tstart_mjd": tstarts[k], "n_time": T,
            "n_chans": N, "total_duration_s": T * tsamp, "bandwidth_mhz": N * 0.0028,
        }
        scans.append((data, freqs, hdr))

    stage1 = assess_arrays(scans[0], scans[1], tile_width=W, top_k=8)
    signals = [
        {"label": f"tile {c['tile_idx']}", "tile_idx": c["tile_idx"], "peak_freq_mhz": c["peak_freq_mhz"],
         "drift_rate_hz_s": c["drift_rate_hz_s"], "t_ref_mjd": c["t_ref_mjd"], "drift_snr": c["drift_snr"]}
        for c in stage1["candidates"]
    ] + [stage1["negative_control"]]
    n = scans_used or len(scans)
    tested = cadence_test_signals(lambda i: scans[i], roles[:n], signals, method=method, tile_width=W, noise=noise)
    by_tile = {s["tile_idx"]: s for s in tested[:-1]}
    control = tested[-1]

    checks = {}
    for tile, _, _, _, present, expected in injections:
        if tile == 190:
            checks["control_tile_190"] = {
                "expected": "RFI", "got": control["cadence_verdict"], "tile": control["tile_idx"],
                "ok": control["tile_idx"] == 190 and control["cadence_verdict"] == "RFI",
            }
            continue
        got = by_tile.get(tile)
        checks[f"tile_{tile}"] = {
            "expected": expected,
            "got": got["cadence_verdict"] if got else "not a Stage 1 candidate",
            "on1_snr": got["cadence_scans"][0]["snr"] if got else None,
            "stage1_drift_snr": got["drift_snr"] if got else None,
            "ok": bool(got) and got["cadence_verdict"] == expected,
        }
    diffs = {s["tile_idx"]: round(s["cadence_scans"][0]["snr"] - s["drift_snr"], 2)
             for s in tested[:-1] if s["cadence_scans"][0]["snr"] is not None}
    max_diff = max((abs(d) for d in diffs.values()), default=float("inf"))
    checks["on1_snr_agreement"] = {
        "expected": f"|cadence ON_1 SNR - Stage 1 drift_snr| <= {SNR_AGREEMENT_TOL} for all {len(tested) - 1}",
        "got": f"max {max_diff:.2f} over {len(diffs)}",
        "diff_by_tile": diffs,
        "ok": len(diffs) == len(tested) - 1 and max_diff <= SNR_AGREEMENT_TOL,
    }
    return {
        "passed": all(c["ok"] for c in checks.values()),
        "method": method,
        "noise": noise,
        "scans_used": n,
        "checks": checks,
        "stage1_candidate_tiles": [c["tile_idx"] for c in stage1["candidates"]],
    }


def synthetic_cadence_scans(
    injections: list[tuple], seed: int, n_scans: int = 6, T: int = 16, N: int = 65536,
    tsamp: float = 18.25, slew: float = 30.0, foff_hz: float = 2800.0, tile_width: int = 256,
) -> list[tuple[np.ndarray, np.ndarray, dict]]:
    """Synthetic (data, freqs, header) scans of an ON/OFF cadence in observing order.
    injections: (tile, chan in tile at scan 0 t=0, channels drifted per (T-1) samples,
    amplitude, set of scan indices where present)."""
    rng = np.random.default_rng(seed)
    span = (T - 1) * tsamp
    t0_mjd = 60000.0
    freqs = 1420.0 + np.arange(N, dtype=np.float64) * (foff_hz / 1e6)
    scans = []
    for k in range(n_scans):
        tstart = t0_mjd + k * (T * tsamp + slew) / 86400.0
        data = rng.normal(loc=100.0, scale=1.0, size=(T, N)).astype(np.float32)
        for tile, c_in, drift, amp, present in injections:
            if k not in present:
                continue
            for t in range(T):
                elapsed = (tstart - t0_mjd) * 86400.0 + t * tsamp
                data[t, int(round(tile * tile_width + c_in + drift * elapsed / span))] += amp
        hdr = {
            "source_name": "SYNTHETIC_EDGE_CASES", "fch1_mhz": float(freqs[0]), "foff_mhz": foff_hz / 1e6,
            "foff_hz": foff_hz, "tsamp_s": tsamp, "tstart_mjd": tstart, "n_time": T,
            "n_chans": N, "total_duration_s": T * tsamp, "bandwidth_mhz": N * foff_hz / 1e6,
        }
        scans.append((data, freqs, hdr))
    return scans


def _direct_signal(scans: list, tile: int, c_in: int, drift_bins: int, tile_width: int = 256) -> dict:
    """A cadence test signal built straight from an injection (bypassing Stage 1), in the
    same form Stage 1 candidates take."""
    _, freqs, hdr = scans[0]
    span = track_span_s(hdr, hdr["n_time"])
    return {
        "peak_freq_mhz": float(freqs[tile * tile_width + c_in]),
        "drift_rate_hz_s": round(drift_bins * hdr["foff_hz"] / span, 3),
        "drift_bins": drift_bins, "max_drift_bins": 10, "t_ref_mjd": hdr["tstart_mjd"],
        "ref_span_s": span, "ref_foff_hz": hdr["foff_hz"],
    }


def run_cadence_edge_case_benchmark() -> dict:
    """
    One case per defect found by the 2026-10-16 Codex review of the cadence check. Each case
    was run against the code as reviewed (d48b19b) and failed there before its fix.
      bug1_unmeasured_scans   cadence_verdict must not count an unmeasured (None) scan as
                              absent: ON/OFF/ON/OFF = True/None/True/None is not PASSES, and
                              True/False/None/False is not ONE-OFF.
      bug2_neighbor_carrier   a signal in every ON, with an unrelated carrier 10 channels from
                              its track in OFF_2 only, must PASS (not be vetoed by the neighbor).
      bug3_band_edge          a carrier 3 channels from the band edge, in every ON, must PASS
                              (not come back unmeasured).
      bug4_drift_bank_edge    a +14-bin/scan drifter in every ON (Stage 1 caps at +/-10) must
                              PASS after the drift is refined.
      bug5_rounded_drift      T=17, 2.8 Hz channels, -8-bin drifter: the cadence SNR in the
                              scan Stage 1 scored must match Stage 1 (the stored drift rate is
                              rounded to 0.001 Hz/s, which moves exact-half rows).
      advisory_gate           gate_verdicts must withhold PASSES when a negative control or a
                              benchmark failed.
    """
    W = 256
    roles4 = ["ON", "OFF", "ON", "OFF"]
    roles6 = ["ON", "OFF", "ON", "OFF", "ON", "OFF"]
    checks = {}

    def run(name, fn):
        try:
            checks[name] = fn()
        except Exception as e:  # a missing function counts as a failing case
            checks[name] = {"ok": False, "got": f"{type(e).__name__}: {e}"}

    def bug1():
        a = cadence_verdict([{"role": r, "present": p} for r, p in zip(roles4, [True, None, True, None])])[0]
        b = cadence_verdict([{"role": r, "present": p} for r, p in zip(roles4, [True, False, None, False])])[0]
        return {"expected": "neither PASSES nor ONE-OFF", "got": f"{a}, {b}", "ok": a != "PASSES" and b != "ONE-OFF"}

    def bug2():
        # signal: tile 60, +3 bins/scan in ON 0,2,4. Neighbor: same drift, +10 channels, OFF_2 (scan 3) only.
        scans = synthetic_cadence_scans([(60, 100, 3.0, 4.0, {0, 2, 4}), (60, 110, 3.0, 8.0, {3})], seed=101)
        sig = _direct_signal(scans, 60, 100, 3)
        res = cadence_test_signals(lambda i: scans[i], roles6, [sig], tile_width=W)[0]
        return {"expected": "PASSES", "got": res["cadence_verdict"],
                "off2": res["cadence_scans"][3], "ok": res["cadence_verdict"] == "PASSES"}

    def bug3():
        scans = synthetic_cadence_scans([(0, 3, 0.0, 4.0, {0, 2, 4})], seed=102)
        sig = _direct_signal(scans, 0, 3, 0)
        res = cadence_test_signals(lambda i: scans[i], roles6, [sig], tile_width=W)[0]
        return {"expected": "PASSES", "got": res["cadence_verdict"],
                "on1": res["cadence_scans"][0], "ok": res["cadence_verdict"] == "PASSES"}

    def bug4():
        scans = synthetic_cadence_scans([(100, 60, 14.0, 8.0, {0, 2, 4})], seed=103)
        stage1 = assess_arrays(scans[0], scans[1], tile_width=W, top_k=4)
        cand = next((c for c in stage1["candidates"] if abs(c["tile_idx"] - 100) <= 1), None)
        if cand is None:
            return {"expected": "PASSES", "got": "not a Stage 1 candidate", "ok": False}
        res = cadence_test_signals(lambda i: scans[i], roles6, [cand], tile_width=W)[0]
        return {"expected": "PASSES", "got": res["cadence_verdict"], "stage1_drift_bins": cand["drift_bins"],
                "snrs": [r["snr"] for r in res["cadence_scans"]], "ok": res["cadence_verdict"] == "PASSES"}

    def bug5():
        scans = synthetic_cadence_scans([(50, 128, -8.0, 5.0, {0})], seed=104, n_scans=2, T=17, foff_hz=2.8)
        stage1 = assess_arrays(scans[0], scans[1], tile_width=W, top_k=4)
        cand = next((c for c in stage1["candidates"] if c["tile_idx"] == 50), None)
        if cand is None:
            return {"expected": "agreement", "got": "not a Stage 1 candidate", "ok": False}
        res = cadence_test_signals(lambda i: scans[i], ["ON", "OFF"], [cand], tile_width=W)[0]
        on1 = res["cadence_scans"][0]["snr"]
        return {"expected": f"|ON_1 SNR - drift_snr| <= {SNR_AGREEMENT_TOL}", "got": f"{on1} vs {cand['drift_snr']}",
                "ok": on1 is not None and abs(on1 - cand["drift_snr"]) <= SNR_AGREEMENT_TOL}

    def advisory():
        cands = [{"cadence_verdict": "PASSES", "cadence_detail": "in 3/3 ON, 0/3 OFF"}]
        gate_verdicts(cands, controls_passed=False, benchmarks_passed=True)
        return {"expected": "PASSES withheld", "got": cands[0]["cadence_verdict"],
                "ok": cands[0]["cadence_verdict"] != "PASSES"}

    for name, fn in (("bug1_unmeasured_scans", bug1), ("bug2_neighbor_carrier", bug2), ("bug3_band_edge", bug3),
                     ("bug4_drift_bank_edge", bug4), ("bug5_rounded_drift", bug5), ("advisory_gate", advisory)):
        run(name, fn)
    return {"passed": all(c["ok"] for c in checks.values()), "checks": checks}


if __name__ == "__main__":
    res = run_synthetic_verification_benchmark()
    print(json.dumps(res, indent=2))
    print(json.dumps(run_noise_calibration_benchmark(), indent=2))
    print(json.dumps(run_synthetic_cadence_benchmark(), indent=2))
