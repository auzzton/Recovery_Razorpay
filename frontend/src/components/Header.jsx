import React from 'react';
import { ShieldCheck, RefreshCw, Layers, Database, Sparkles } from 'lucide-react';

export default function Header({ merchants, selectedMerchant, onSelectMerchant, onReSeed, isLoading }) {
  return (
    <header className="glass-panel" style={{ padding: '20px 28px', marginBottom: '24px', borderRadius: '20px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '16px' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '4px' }}>
            <div style={{ 
              background: 'linear-gradient(135deg, #3b82f6 0%, #8b5cf6 100%)', 
              padding: '8px', 
              borderRadius: '12px', 
              display: 'flex', 
              boxShadow: '0 0 20px rgba(59, 130, 246, 0.4)' 
            }}>
              <ShieldCheck size={26} color="#ffffff" />
            </div>
            <h1 style={{ fontSize: '1.75rem', fontWeight: 800, letterSpacing: '-0.02em' }}>
              Recovery<span className="gradient-text">OS</span>
            </h1>
            <span className="badge badge-recovered" style={{ marginLeft: '4px' }}>
              <Sparkles size={12} /> Decoupled Engine Active
            </span>
          </div>
          <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
            AI Revenue Recovery Agent & Orchestrator — Razorpay Buildathon (Track 03)
          </p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          {/* Merchant Filter Dropdown */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', background: 'rgba(255, 255, 255, 0.05)', padding: '6px 14px', borderRadius: '12px', border: '1px solid var(--border-card)' }}>
            <Layers size={16} color="var(--text-secondary)" />
            <span style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', fontWeight: 600 }}>Merchant:</span>
            <select 
              value={selectedMerchant} 
              onChange={(e) => onSelectMerchant(e.target.value)}
              style={{
                background: 'transparent',
                color: 'var(--text-primary)',
                border: 'none',
                outline: 'none',
                fontWeight: 700,
                fontSize: '0.9rem',
                cursor: 'pointer'
              }}
            >
              <option value="ALL" style={{ background: '#121824', color: '#fff' }}>All Merchants (Multi-Tenant)</option>
              {merchants.map(m => (
                <option key={m} value={m} style={{ background: '#121824', color: '#fff' }}>{m}</option>
              ))}
            </select>
          </div>

          {/* Seed Dataset Button */}
          <button 
            onClick={onReSeed} 
            disabled={isLoading}
            className="btn-secondary"
            style={{ padding: '8px 14px', fontSize: '0.85rem' }}
          >
            <RefreshCw size={14} className={isLoading ? 'spin' : ''} />
            Re-seed Batch (100 Events)
          </button>
        </div>
      </div>
    </header>
  );
}
