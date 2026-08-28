import React from 'react';
import { IndianRupee, TrendingUp, ShieldAlert, Award, DollarSign, PieChart, Zap } from 'lucide-react';

export default function HeroMetrics({ summary }) {
  if (!summary) return null;

  const formatRupees = (val) => {
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR',
      maximumFractionDigits: 0
    }).format(val || 0);
  };

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '16px', marginBottom: '24px' }}>
      {/* 1. At Risk */}
      <div className="glass-panel" style={{ padding: '20px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', fontWeight: 600 }}>Revenue At Risk</span>
          <ShieldAlert size={20} color="#f43f5e" />
        </div>
        <div style={{ fontSize: '1.6rem', fontWeight: 800, color: '#f8fafc' }} className="font-mono">
          {formatRupees(summary.revenue_at_risk_rupees)}
        </div>
        <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '4px' }}>
          {summary.total_events} failed events ingested
        </div>
      </div>

      {/* 2. Natural Recovery (Counterfactual Baseline) */}
      <div className="glass-panel" style={{ padding: '20px', borderLeft: '4px solid #64748b' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', fontWeight: 600 }}>Natural Recovery Baseline</span>
          <PieChart size={20} color="#94a3b8" />
        </div>
        <div style={{ fontSize: '1.6rem', fontWeight: 800, color: '#94a3b8' }} className="font-mono">
          {formatRupees(summary.natural_recovery_rupees)}
        </div>
        <div style={{ fontSize: '0.75rem', color: '#94a3b8', marginTop: '4px' }}>
          ~{summary.natural_recovery_pct}% (RBI NACH benchmark)
        </div>
      </div>

      {/* 3. RecoveryOS Outcome */}
      <div className="glass-panel" style={{ padding: '20px', borderLeft: '4px solid #3b82f6' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', fontWeight: 600 }}>RecoveryOS Recovered</span>
          <TrendingUp size={20} color="#60a5fa" />
        </div>
        <div style={{ fontSize: '1.6rem', fontWeight: 800, color: '#60a5fa' }} className="font-mono">
          {formatRupees(summary.recovery_os_recovered_rupees)}
        </div>
        <div style={{ fontSize: '0.75rem', color: '#60a5fa', marginTop: '4px' }}>
          {summary.recovery_os_rate_pct}% gross recovery rate
        </div>
      </div>

      {/* 4. Incremental AI Delta (Headline Number) */}
      <div className="glass-panel" style={{ padding: '20px', background: 'rgba(16, 185, 129, 0.08)', border: '1px solid rgba(16, 185, 129, 0.3)' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
          <span style={{ fontSize: '0.8rem', color: '#34d399', fontWeight: 700 }}>Incremental AI Delta</span>
          <Award size={20} color="#34d399" />
        </div>
        <div style={{ fontSize: '1.6rem', fontWeight: 800, color: '#34d399' }} className="font-mono">
          {formatRupees(summary.incremental_ai_delta_rupees)}
        </div>
        <div style={{ fontSize: '0.75rem', color: '#34d399', marginTop: '4px', fontWeight: 600 }}>
          +{summary.incremental_rate_pct}% net value created by AI
        </div>
      </div>

      {/* 5. Net Revenue Gain & ROI */}
      <div className="glass-panel" style={{ padding: '20px', background: 'rgba(139, 92, 246, 0.08)', border: '1px solid rgba(139, 92, 246, 0.3)' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
          <span style={{ fontSize: '0.8rem', color: '#c084fc', fontWeight: 700 }}>Net Gain / ROI</span>
          <Zap size={20} color="#c084fc" />
        </div>
        <div style={{ fontSize: '1.6rem', fontWeight: 800, color: '#c084fc' }} className="font-mono">
          {formatRupees(summary.net_revenue_gain_rupees)}
        </div>
        <div style={{ fontSize: '0.75rem', color: '#c084fc', marginTop: '4px', fontWeight: 700 }}>
          Cost: {formatRupees(summary.total_intervention_cost_rupees)} • ROI: {summary.roi_pct > 0 ? `${summary.roi_pct}%` : '∞'}
        </div>
      </div>
    </div>
  );
}
