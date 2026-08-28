import React, { useState } from 'react';
import { Send, MessageSquare, ShieldAlert, Sparkles, AlertTriangle } from 'lucide-react';

export default function ReplySimulator({ workflows, onRefresh }) {
  const [selectedWfId, setSelectedWfId] = useState('');
  const [messageText, setMessageText] = useState('');
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  // Filter workflows eligible for outreach simulator
  const activeWorkflows = workflows.filter(w => !w.is_terminal || w.current_state === 'DNC_LOCKED');

  const handleSend = async (customMsg = null) => {
    const textToSend = customMsg || messageText;
    if (!selectedWfId || !textToSend.trim()) return;

    setLoading(true);
    setResult(null);

    try {
      const res = await fetch('/api/simulator/reply', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          workflow_id: selectedWfId,
          message_text: textToSend
        })
      });
      const data = await res.json();
      setResult(data);
      setLoading(false);
      onRefresh();
    } catch (err) {
      console.error(err);
      setLoading(false);
    }
  };

  const handleTriggerBreach = async () => {
    if (!selectedWfId) return;
    setLoading(true);
    try {
      const res = await fetch(`/api/simulator/trigger-breach?workflow_id=${selectedWfId}`, {
        method: 'POST'
      });
      const data = await res.json();
      setResult(data);
      setLoading(false);
      onRefresh();
    } catch (err) {
      console.error(err);
      setLoading(false);
    }
  };

  return (
    <div className="glass-panel" style={{ padding: '24px', borderRadius: '16px', marginBottom: '24px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '16px' }}>
        <MessageSquare size={22} color="#8b5cf6" />
        <h3 style={{ fontSize: '1.1rem', fontWeight: 700 }}>
          Interactive Outreach & Opt-Out Reply Simulator
        </h3>
        <span className="badge badge-escalated">Compliance Simulator</span>
      </div>

      <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem', marginBottom: '16px' }}>
        Test how the deterministic <strong>System Guard</strong> handles customer replies. Type opt-out keywords (e.g. <code>"band karo"</code> or <code>"stop"</code>) to watch outreach halt immediately with zero compliance risk.
      </p>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 2fr', gap: '16px', flexWrap: 'wrap' }}>
        {/* Select Workflow */}
        <div>
          <label style={{ display: 'block', fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-secondary)', marginBottom: '6px' }}>
            Select Target Customer Event:
          </label>
          <select 
            value={selectedWfId}
            onChange={(e) => setSelectedWfId(e.target.value)}
            style={{
              width: '100%',
              padding: '10px',
              borderRadius: '8px',
              background: 'rgba(255,255,255,0.05)',
              border: '1px solid var(--border-card)',
              color: '#fff',
              fontSize: '0.85rem'
            }}
          >
            <option value="">-- Choose a workflow --</option>
            {activeWorkflows.slice(0, 15).map(w => (
              <option key={w.workflow_id} value={w.workflow_id}>
                {w.customer_name} ({w.current_state}) - ₹{w.amount_in_cents / 100}
              </option>
            ))}
          </select>
        </div>

        {/* Reply Input */}
        <div>
          <label style={{ display: 'block', fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-secondary)', marginBottom: '6px' }}>
            Simulate Customer WhatsApp Reply:
          </label>
          <div style={{ display: 'flex', gap: '8px' }}>
            <input 
              type="text"
              placeholder="e.g., 'band karo' or 'Pay on Friday'"
              value={messageText}
              onChange={(e) => setMessageText(e.target.value)}
              style={{
                flex: 1,
                padding: '10px 14px',
                borderRadius: '8px',
                background: 'rgba(255,255,255,0.05)',
                border: '1px solid var(--border-card)',
                color: '#fff',
                fontSize: '0.85rem'
              }}
            />
            <button 
              className="btn-primary" 
              onClick={() => handleSend()}
              disabled={loading || !selectedWfId}
              style={{ padding: '8px 16px', fontSize: '0.85rem' }}
            >
              <Send size={14} /> Send Reply
            </button>
          </div>
        </div>
      </div>

      {/* Quick Test Chips */}
      <div style={{ display: 'flex', gap: '8px', marginTop: '12px', alignItems: 'center', flexWrap: 'wrap' }}>
        <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Quick Presets:</span>
        <button 
          className="btn-secondary" 
          onClick={() => { setMessageText("band karo"); handleSend("band karo"); }}
          style={{ padding: '4px 10px', fontSize: '0.75rem', color: '#fb7185', borderColor: 'rgba(244,63,94,0.3)' }}
        >
          <ShieldAlert size={12} /> "band karo" (Hindi Opt-out)
        </button>
        <button 
          className="btn-secondary" 
          onClick={() => { setMessageText("Pay on Friday"); handleSend("Pay on Friday"); }}
          style={{ padding: '4px 10px', fontSize: '0.75rem', color: '#fbbf24', borderColor: 'rgba(245,158,11,0.3)' }}
        >
          <Sparkles size={12} /> "Pay on Friday" (Promise)
        </button>
        <button 
          className="btn-secondary" 
          onClick={handleTriggerBreach}
          disabled={!selectedWfId}
          style={{ padding: '4px 10px', fontSize: '0.75rem', color: '#c084fc', borderColor: 'rgba(139,92,246,0.3)' }}
        >
          <AlertTriangle size={12} /> Trigger Promise Breach Check (+2h)
        </button>
      </div>

      {/* Result Display */}
      {result && (
        <div style={{ 
          marginTop: '16px', 
          padding: '12px 16px', 
          borderRadius: '8px',
          background: result.status === 'GUARD_BLOCKED' ? 'rgba(244, 63, 94, 0.1)' : 'rgba(16, 185, 129, 0.1)',
          border: result.status === 'GUARD_BLOCKED' ? '1px solid rgba(244, 63, 94, 0.3)' : '1px solid rgba(16, 185, 129, 0.3)',
          fontSize: '0.85rem'
        }}>
          <div style={{ fontWeight: 700, color: result.status === 'GUARD_BLOCKED' ? '#fb7185' : '#34d399' }}>
            {result.message}
          </div>
          {result.workflow && (
            <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: '4px' }}>
              New State: <strong style={{ color: '#fff' }}>{result.workflow.current_state}</strong> • Terminal: {result.workflow.is_terminal ? 'Yes' : 'No'}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
