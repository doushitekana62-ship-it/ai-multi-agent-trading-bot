import { useEffect, useRef } from 'react';
import axios from 'axios';
import toast from 'react-hot-toast';
import { useAuth } from '../context/AuthContext';

const POLL_MS = 15000;

export default function CycleUpdateToast() {
  const { isAuthenticated, loading } = useAuth();
  const lastCycleRef = useRef(null);

  useEffect(() => {
    if (loading || !isAuthenticated) return undefined;

    let cancelled = false;

    const check = async () => {
      try {
        const response = await axios.get('/api/dashboard/status', {
          params: { _ts: Date.now() },
          headers: { 'Cache-Control': 'no-cache' },
        });
        if (cancelled) return;

        const cycles = Number(response.data?.cycles_today);
        if (!Number.isFinite(cycles)) return;

        if (lastCycleRef.current === null) {
          lastCycleRef.current = cycles;
          return;
        }

        if (cycles > lastCycleRef.current) {
          const delta = cycles - lastCycleRef.current;
          lastCycleRef.current = cycles;
          for (let index = 0; index < delta; index += 1) {
            toast('1 cycle is update', {
              duration: 2200,
              position: 'top-right',
            });
          }
        } else if (cycles < lastCycleRef.current) {
          lastCycleRef.current = cycles;
        }
      } catch {
        // Dashboard polling already reports API failures. This notifier stays silent.
      }
    };

    check();
    const timer = window.setInterval(check, POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [isAuthenticated, loading]);

  return null;
}
