import { useCallback, useEffect, useState } from "react";
import type { OcrCalibrationRegionDto, OcrCalibrationSnapshotDto } from "@desktop/shared";
import { getZml } from "../zml";
import "./calibrationView.css";

export function CalibrationView() {
  const [snapshot, setSnapshot] = useState<OcrCalibrationSnapshotDto | null>(null);
  const [loading, setLoading] = useState(false);
  const [recalibrating, setRecalibrating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const value = await getZml().getOcrCalibration();
      setSnapshot(value);
    } catch (cause) {
      setError(toErrorMessage(cause));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const recalibrate = useCallback(async () => {
    setRecalibrating(true);
    setError(null);
    setMessage(null);
    try {
      const result = await getZml().recalibrateOcr();
      setMessage(result.message);
      await delay(1_800);
      await refresh();
    } catch (cause) {
      setError(toErrorMessage(cause));
    } finally {
      setRecalibrating(false);
    }
  }, [refresh]);

  return (
    <div className="zml-calibration-view">
      <div className="zml-calibration-header">
        <div>
          <h2>OCR Calibration</h2>
          <p>
            Fresh Finder and Compass detection previews. The screenshots include context outside the
            detected outer box, so clipping on either side is visible instead of hidden by the crop.
          </p>
        </div>
        <div className="zml-calibration-actions">
          <button
            type="button"
            className="zml-button"
            onClick={() => void refresh()}
            disabled={loading || recalibrating}
          >
            {loading ? "Capturing..." : "Refresh screenshots"}
          </button>
          <button
            type="button"
            className="zml-button zml-button-primary"
            onClick={() => void recalibrate()}
            disabled={loading || recalibrating}
          >
            {recalibrating ? "Recalibrating..." : "Recalibrate OCR"}
          </button>
        </div>
      </div>

      <div className="zml-calibration-legend" aria-label="Calibration overlay legend">
        <span><i className="is-outer" />Outer detected region</span>
        <span><i className="is-details" />Finder details / Lon</span>
        <span><i className="is-status" />Status / Lat</span>
        <span><i className="is-radar" />Radar geometry</span>
      </div>

      {error && <div className="zml-calibration-error">{error}</div>}
      {message && <div className="zml-calibration-message">{message}</div>}

      <div className="zml-calibration-grid">
        <CalibrationCard
          title="Finder"
          subtitle="Outer Finder bbox + RADAR / MODES / DETAILS / STATUS / UNITS"
          region={snapshot?.finder ?? null}
          loading={loading && snapshot === null}
        />
        <CalibrationCard
          title="Compass"
          subtitle="Outer Compass bbox + detected radar circle + Lon / Lat OCR boxes"
          region={snapshot?.compass ?? null}
          loading={loading && snapshot === null}
        />
      </div>

      <div className="zml-calibration-note">
        <strong>What to check:</strong> if Finder UI pixels continue outside the red FINDER box, the
        locator crop is wrong. If the complete Finder is inside red but the resource text leaves the
        DETAILS box, the inner OCR bbox is wrong. If both boxes contain the full text, the problem is
        OCR/preprocessing rather than geometry.
      </div>
    </div>
  );
}

function CalibrationCard({
  title,
  subtitle,
  region,
  loading,
}: {
  title: string;
  subtitle: string;
  region: OcrCalibrationRegionDto | null;
  loading: boolean;
}) {
  const rect = region?.rect ?? null;
  return (
    <section className="zml-calibration-card">
      <div className="zml-calibration-card-head">
        <div>
          <h3>{title}</h3>
          <p>{subtitle}</p>
        </div>
        {region?.available && (
          <span className="zml-calibration-confidence">
            {formatConfidence(region.confidence)}
          </span>
        )}
      </div>

      <div className="zml-calibration-preview">
        {region?.available && region.imageDataUrl ? (
          <img src={region.imageDataUrl} alt={`${title} calibration with OCR bounding boxes`} />
        ) : (
          <div className="zml-calibration-placeholder">
            {loading ? "Capturing..." : "Region not detected in the current Entropia window."}
          </div>
        )}
      </div>

      <div className="zml-calibration-meta">
        <span>Rect: {rect ? rect.join(", ") : "—"}</span>
        <span>Scale: {formatScale(region?.scale)}</span>
        <span>Captured: {formatTimestamp(region?.capturedTsMs)}</span>
      </div>
    </section>
  );
}

function formatConfidence(value: number | null | undefined): string {
  return value === null || value === undefined ? "confidence —" : `confidence ${value.toFixed(3)}`;
}

function formatScale(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : value.toFixed(3);
}

function formatTimestamp(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return new Date(value).toLocaleTimeString();
}

function toErrorMessage(value: unknown): string {
  return value instanceof Error ? value.message : String(value);
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
