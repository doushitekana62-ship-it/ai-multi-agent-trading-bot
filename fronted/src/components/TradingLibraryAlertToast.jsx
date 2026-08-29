import { useEffect, useRef } from 'react';
import axios from 'axios';
import toast from 'react-hot-toast';

const POLL_MS = 5000;
const ALERT_DURATION = 6500;
const ALERT_MARKER = 'LIBRARY_ALERTS_JSON=';

const normalizeAlerts = (value) => {
  if (!Array.isArray(value)) return [];
  return value
    .filter((item) => item && typeof item === 'object')
    .map((item) => ({
      id: String(item.id || item.type || item.title || 'library-alert'),
      type: String(item.type || 'LIBRARY').toUpperCase(),
      title: String(item.title || 'Trading Library Alert'),
      message: String(item.message || item.description || 'Opportunity detected by the Trading Library.'),
      direction: String(item.direction || 'NEUTRAL').toUpperCase(),
      confidence: Number(item.confidence || 0),
    }))
    .slice(0, 4);
};

const extractEmbeddedAlerts = (reasoning) => {
  const text = String(reasoning || '');
  const markerIndex = text.indexOf(ALERT_MARKER);
  if (markerIndex < 0) return [];
  try {
    return normalizeAlerts(JSON.parse(text.slice(markerIndex + ALERT_MARKER.length).trim()));
  } catch {
    return [];
  }
};

function AlertCard({ alert }) {
  const direction = alert.direction === 'BUY' ? '#35c759' : alert.direction === 'SELL' ? '#ff5c5c' : '#8b949e';
  const confidence = Math.max(0, Math.min(100, alert.confidence <= 1 ? alert.confidence * 100 : alert.confidence));
  return (
    <div style={{ width: 'min(360px, calc(100vw - 28px))', padding: '12px 14px', borderRadius: 12, border: `1px solid ${direction}55`, background: 'rgba(15, 20, 23, .96)', color: '#f5f7f8', boxShadow: '0 12px 32px rgba(0,0,0,.28)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center' }}>
        <strong style={{ fontSize: 13 }}>{alert.title}</strong>
        <span style={{ color: direction, fontWeight: 700, fontSize: 11 }}>{alert.direction}</span>
      </div>
      <div style={{ marginTop: 6, fontSize: 12, lineHeight: 1.45, opacity: .88 }}>{alert.message}</div>
      <div style={{ marginTop: 7, fontSize: 10, opacity: .62 }}>{alert.type} · confidence {confidence.toFixed(0)}%</div>
    </div>
  );
}

export default function TradingLibraryAlertToast() {
  const lastFingerprintRef = useRef('');
  const initializedRef = useRef(false);

  useEffect(() => {
    let cancelled = false;
    let inFlight = false;

    const check = async () => {
      if (cancelled || inFlight) return;
      inFlight = true;
      try {
        const response = await axios.get('/api/dashboard/recent-decision', {
          params: { _ts: Date.now() },
          headers: { 'Cache-Control': 'no-cache' },
          timeout: 8000,
        });
        if (cancelled) return;
        const decision = response.data?.decision || {};
        const alerts = normalizeAlerts(decision.library_alerts || decision.analysis?.library_alerts).concat(
          extractEmbeddedAlerts(decision.reasoning),
        ).slice(0, 4);
        const cycleKey = String(decision.created_at || '');
        const fingerprint = JSON.stringify({ cycleKey, alerts });

        if (!initializedRef.current) {
          initializedRef.current = true;
          lastFingerprintRef.current = fingerprint;
          return;
        }
        if (!alerts.length || fingerprint === lastFingerprintRef.current) return;
        lastFingerprintRef.current = fingerprint;

        alerts.forEach((alert) => {
          toast.custom(() => <AlertCard alert={alert} />, {
            id: `library-${cycleKey}-${alert.id}`,
            duration: ALERT_DURATION,
            position: 'top-left',
          });
        });
      } catch {
        // Optional alert feed failure must never block dashboard operation.
      } finally {
        inFlight = false;
      }
    };

    check();
    const timer = window.setInterval(check, POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  return null;
}
