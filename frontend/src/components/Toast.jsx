import { useState, useCallback, useEffect, useRef } from 'react';

export function useToast() {
  const [toast, setToast] = useState(null);
  const timerRef = useRef(null);

  const showToast = useCallback((message, type) => {
    if (timerRef.current) clearTimeout(timerRef.current);
    setToast({ message, type });
    timerRef.current = setTimeout(() => setToast(null), 3000);
  }, []);

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  return { toast, showToast };
}

export default function Toast({ toast }) {
  if (!toast) return null;

  return (
    <div className={`toast-popup toast-${toast.type}`}>
      {toast.message}
    </div>
  );
}
