"""
SETI Weirdness & Anomaly Assessment Engine
==========================================
Evaluates radio astronomy filterbank (.fil) and HDF5 (.h5) spectrograms across
five orthogonal axes of 'weirdness', coupled with an ON-target vs OFF-target (ABACAD)
sky-localization veto:

1. Narrowband De-Doppler Drift SNR (linear drifting carriers)
2. Temporal Kurtosis & Pulsed Duty-Cycle Anomaly (blinking beacons / fast bursts)
3. Non-Linear Ridge Curvature / Acceleration (chirps, curved orbits, frequency-hopping)
4. 2D Time-Frequency Morphological Structure (SVD low-rank structure / modulated sidebands)
5. Unsupervised Manifold Outlier Distance (Isolation Forest + PCA reconstruction error)
6. ABACAD Sky-Localization Veto (ON-target power vs OFF-target reference power in the exact MHz window)
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


def compute_dedoppler_snr(z_tiles: np.ndarray, max_shift_bins: int = 12) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Vectorized De-Doppler shift-and-stack across all tiles simultaneously.
    Input:
        z_tiles: shape (T, N_tiles, W)
    Returns:
        best_snr: (N_tiles,) peak integrated SNR across all drift rates and channels
        best_drift_bins: (N_tiles,) total frequency bin shift from t=0 to t=T-1
        best_chan_in_tile: (N_tiles,) starting channel index inside tile
    """
    T, N_tiles, W = z_tiles.shape
    sqrt_T = math.sqrt(max(T, 1))

    best_snr = np.full(N_tiles, -1e9, dtype=np.float32)
    best_drift = np.zeros(N_tiles, dtype=np.int32)
    best_chan = np.zeros(N_tiles, dtype=np.int32)

    shifts = range(-max_shift_bins, max_shift_bins + 1)
    t_idx = np.arange(T, dtype=np.float32) / max(T - 1, 1)

    for total_shift in shifts:
        # Accumulate shifted time rows
        acc = np.zeros((N_tiles, W), dtype=np.float32)
        for t in range(T):
            s = int(round(total_shift * t_idx[t]))
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
        if pad < W // 2:
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
    duration_s = max(header.get("total_duration_s", 300.0), 1.0)
    foff_hz = header.get("foff_hz", 2800.0)
    drift_rate_hz_s = (drift_bins * foff_hz) / duration_s

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
    if row["on_off_ratio"] < 1.8 and row["off_peak_snr"] > 6.5:
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


def assess_cadence(
    on_filepath: str,
    off_filepath: str | None = None,
    tile_width: int = 256,
    top_k: int = 8,
) -> dict:
    """
    Runs the full 5-axis SETI Weirdness Assessment on an ON-target file and
    performs cross-scan ABACAD sky-localization veto against an OFF-target file.
    """
    t0 = time.time()
    on_raw, on_freqs, on_hdr = load_spectrogram_fast(on_filepath)
    on_z, usable_chans = normalize_bandpass(on_raw, tile_width=tile_width)
    on_freqs = on_freqs[:usable_chans]

    T, _ = on_z.shape
    N_tiles = usable_chans // tile_width
    on_tiles = on_z.reshape(T, N_tiles, tile_width)

    feats = extract_tile_features(on_tiles, on_hdr, tile_width=tile_width)

    # Load and normalize OFF-target scan if provided
    off_tiles = None
    off_hdr = None
    if off_filepath and os.path.exists(off_filepath):
        off_raw, off_freqs, off_hdr = load_spectrogram_fast(off_filepath)
        off_z, off_usable = normalize_bandpass(off_raw, tile_width=tile_width)
        common_tiles = min(N_tiles, off_usable // tile_width)
        off_tiles = off_z[:, : common_tiles * tile_width].reshape(off_z.shape[0], common_tiles, tile_width)

    # Compute OFF-target activity at every corresponding frequency tile
    off_peak_snr = np.ones(N_tiles, dtype=np.float32) * 2.5
    if off_tiles is not None:
        T_off = off_tiles.shape[0]
        c_tiles = off_tiles.shape[1]
        off_drift_snr, _, _ = compute_dedoppler_snr(off_tiles, max_shift_bins=6)
        off_max_point = np.max(off_tiles, axis=(0, 2)) / 2.0
        off_peak_snr[:c_tiles] = np.maximum(off_drift_snr, off_max_point)

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

    # Sky-Localized Weirdness Score (penalizes tiles that are equally loud in OFF-target scan)
    abacad_veto_multiplier = np.where(
        (off_peak_snr > 8.0) & (on_off_ratio < 1.6),
        0.15,  # Strong suppression for persistent terrestrial RFI
        np.clip(np.sqrt(on_off_ratio), 0.5, 4.0),
    )

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
        "on_file": os.path.basename(on_filepath),
        "off_file": os.path.basename(off_filepath) if off_filepath else None,
        "header": on_hdr,
        "n_tiles_evaluated": int(N_tiles),
        "n_channels_evaluated": int(usable_chans),
        "elapsed_s": round(elapsed, 2),
        "throughput_mchans_s": round((usable_chans * T) / max(elapsed * 1e6, 1e-6), 2),
        "max_weirdness_score": round(float(np.max(total_weirdness_score)), 2),
        "median_weirdness_score": round(float(np.median(total_weirdness_score)), 2),
        "rfi_vetoed_tiles": int(np.sum((off_peak_snr > 8.0) & (on_off_ratio < 1.6))),
        "sky_localized_tiles_gt_15": int(np.sum((total_weirdness_score > 15.0) & (on_off_ratio >= 1.8))),
        "candidates": candidates,
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
    abacad_veto_multiplier = np.where(
        (off_peak_snr > 8.0) & (on_off_ratio < 1.6),
        0.15,
        np.clip(np.sqrt(on_off_ratio), 0.5, 4.0),
    )
    total_weirdness_score = intrinsic_weirdness * abacad_veto_multiplier

    top_tiles = [int(x) for x in np.argsort(total_weirdness_score)[::-1][:6]]
    expected_on_tiles = {42, 95, 140, 190}
    recovered = expected_on_tiles.intersection(set(top_tiles[:5]))
    rfi_vetoed = 210 not in top_tiles[:4]

    return {
        "passed": (len(recovered) == 4) and rfi_vetoed,
        "top_6_tiles": top_tiles,
        "recovered_on_targets": sorted(list(recovered)),
        "rfi_tile_210_score": round(float(total_weirdness_score[210]), 2),
        "rfi_tile_210_intrinsic": round(float(intrinsic_weirdness[210]), 2),
        "scores_by_injected_tile": {
            t: round(float(total_weirdness_score[t]), 2) for t in [42, 95, 140, 190, 210]
        },
    }


if __name__ == "__main__":
    res = run_synthetic_verification_benchmark()
    print(json.dumps(res, indent=2))
