"use client";

import { createContext, ReactNode, useCallback, useContext, useEffect, useState } from "react";
import { CheckCircle2, Info, X } from "lucide-react";

type Toast = { id: number; message: string; tone: "success" | "info" };
const ToastContext = createContext<(message: string, tone?: Toast["tone"]) => void>(() => {});

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const notify = useCallback((message: string, tone: Toast["tone"] = "info") => {
    setToasts((list) => [...list.slice(-2), { id: Date.now() + Math.random(), message, tone }]);
  }, []);
  const dismiss = useCallback((id: number) => setToasts((list) => list.filter((toast) => toast.id !== id)), []);

  return (
    <ToastContext.Provider value={notify}>
      {children}
      <div className="toast-region" role="status" aria-live="polite">
        {toasts.map((toast) => <ToastItem key={toast.id} toast={toast} onDismiss={dismiss} />)}
      </div>
    </ToastContext.Provider>
  );
}

function ToastItem({ toast, onDismiss }: { toast: Toast; onDismiss: (id: number) => void }) {
  useEffect(() => {
    const timer = window.setTimeout(() => onDismiss(toast.id), 5000);
    return () => window.clearTimeout(timer);
  }, [toast.id, onDismiss]);
  return (
    <div className={`toast toast-${toast.tone}`}>
      {toast.tone === "success" ? <CheckCircle2 size={16} aria-hidden="true" /> : <Info size={16} aria-hidden="true" />}
      <span>{toast.message}</span>
      <button type="button" className="icon-button" aria-label="Dismiss message" onClick={() => onDismiss(toast.id)}><X size={14} aria-hidden="true" /></button>
    </div>
  );
}

export const useToast = () => useContext(ToastContext);
