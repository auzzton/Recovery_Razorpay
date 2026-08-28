import React, { useEffect, useState } from 'react';
import { X, ShieldCheck, Clock, User, Cpu, ArrowRight, FileText } from 'lucide-react';

export default function AuditDrawer({ workflowId, onClose }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!workflowId) return;
    setLoading(true);
    fetch(`/api/workflows/${workflowId}/audit`)
      .then(res => res.json())
      .then(d => {
        setData(d);
        setLoading(false);
      })
      .catch(err => {
        console.error(err);
        setLoading(false);
      });
  }, [workflowId]);

  if (!workflowId) return null;

  const formatRupees = (cents) => {
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR',
      maximumFractionDigits: 0
    }).format((cents || 0) / 100);
  };

  return (
    <div style={{
      position: 'fixed',
      top: 0, right: 0, bottom: 0,
      width: '520px',
      maxWidth: '90vw',
      background: '#0d111a',
      borderLeft: '1px solid var(--border-card)',
      boxShadow: '-10px 0 40px rgba(0,0,0,0.8)',
      zIndex: 1000,
      display: 'flex',
      flexDirection: 'column',
      padding: '24px',
      overflowY: 'auto'
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px', paddingBottom: '16px', borderBottom: '1px solid var(--border-card)' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <FileText size={20} color="#60a5fa" />
            <h3 style={{ fontSize: '1.2rem', fontWeight: 700 }}>Audit Ledger History</h3>
          </div>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Immutable append-only judicial log</span>
        </div>
        <button onClick={onClose} style={{ background: 'transparent', border: 'none', color: 'var(--text-muted)', cursor: 'pointer' }}>
          <X size={20} />
        </button>
      </div>

      {loading ? (
        <div style={{ color: 'var(--text-muted)', padding: '40px 0', textAlign: 'center' }}>Loading audit records...</div>
      ) : data ? (
        <div>
          {/* Customer & Workflow summary box */}
          <div style={{ background: 'rgba(255, 255, 255, 0.03)', padding: '16px', borderRadius: '12px', marginBottom: '24px', border: '1px solid var(--border-card)' }}>
            <div style={{ fontWeight: 700, fontSize: '1rem', color: '#f8fafc', marginBottom: '4px' }}>{data.workflow.customer_name}</div>
            <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
              {data.workflow.merchant_id} • Amount: <strong style={{ color: '#34d399' }}>{formatRupees(data.workflow.amount_in_cents)}</strong>
            </div>
            <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: '4px' }}>
              Failure Code: <span className="font-mono" style={{ color: '#60a5fa' }}>{data.workflow.failure_code}</span>
            </div>
          </div>

          {/* Audit Trail Timeline */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            {data.audit_logs.map((log) => (
              <div key={log.id} style={{ 
                background: log.actor === 'SYSTEM_GUARD' ? 'rgba(244, 63, 94, 0.05)' : 'rgba(59, 130, 246, 0.05)',
                border: log.actor === 'SYSTEM_GUARD' ? '1px solid rgba(244, 63, 94, 0.2)' : '1px solid rgba(59, 130, 246, 0.2)',
                borderRadius: '12px',
                padding: '16px'
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                  <span className="badge" style={{ 
                    background: log.actor === 'SYSTEM_GUARD' ? 'rgba(244, 63, 94, 0.2)' : 'rgba(59, 130, 246, 0.2)',
                    color: log.actor === 'SYSTEM_GUARD' ? '#fb7185' : '#60a5fa'
                  }}>
                    {log.actor === 'SYSTEM_GUARD' ? <ShieldCheck size={12} /> : <Cpu size={12} />}
                    {log.actor}
                  </span>
                  <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>
                    {log.created_at ? new Date(log.created_at).toLocaleTimeString() : ''}
                  </span>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.85rem', fontWeight: 700, margin: '8px 0' }}>
                  <span style={{ color: 'var(--text-secondary)' }}>{log.from_state}</span>
                  <ArrowRight size={14} color="var(--text-muted)" />
                  <span style={{ color: '#34d399' }}>{log.to_state}</span>
                </div>

                <div style={{ fontSize: '0.825rem', color: 'var(--text-primary)', lineHeight: 1.4, marginBottom: '8px' }}>
                  {log.reasoning}
                </div>

                <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'flex', gap: '12px' }}>
                  <span>Trigger: <strong style={{ color: '#94a3b8' }}>{log.trigger_type}</strong></span>
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}
