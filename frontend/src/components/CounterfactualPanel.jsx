import React from 'react';
import { CheckCircle2, AlertCircle, Info, Scale } from 'lucide-react';

export default function CounterfactualPanel({ summary }) {
  if (!summary) return null;

  const formatRupees = (val) => {
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR',
      maximumFractionDigits: 0
    }).format(val || 0);
  };

  return (
    <div className="glass-panel" style={{ padding: '24px', marginBottom: '24px', borderRadius: '16px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '16px' }}>
        <Scale size={22} color="#60a5fa" />
        <h3 style={{ fontSize: '1.1rem', fontWeight: 700 }}>
          Counterfactual Baseline Panel (Judicial Proof Engine)
        </h3>
        <span className="badge badge-triaged">Court-Admissible Metric</span>
      </div>

      <p style={{ color: 'var(--text-secondary)', fontSize: '0.875rem', marginBottom: '20px', lineHeight: 1.5 }}>
        Without a counterfactual baseline, gross recovery metrics are unpersuasive ("Would those payments have succeeded anyway?"). 
        RecoveryOS benchmarks every batch against the RBI NACH return rate (~12% natural recovery) to prove exact incremental AI delta.
      </p>

      <div style={{ overflowX: 'auto' }}>
        <table>
          <thead>
            <tr>
              <th>Metric</th>
              <th>Value</th>
              <th>Benchmark & Explanation</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td style={{ fontWeight: 600, color: 'var(--text-primary)' }}>Revenue At Risk</td>
              <td className="font-mono" style={{ fontWeight: 700 }}>{formatRupees(summary.revenue_at_risk_rupees)}</td>
              <td style={{ color: 'var(--text-muted)' }}>{summary.total_events} failed Razorpay events ingested</td>
            </tr>
            <tr>
              <td style={{ fontWeight: 600, color: '#94a3b8' }}>Natural Recovery Baseline</td>
              <td className="font-mono" style={{ fontWeight: 700, color: '#94a3b8' }}>
                ~12% ({formatRupees(summary.natural_recovery_rupees)})
              </td>
              <td style={{ color: 'var(--text-muted)' }}>RBI NACH return benchmark — what recovers with zero intervention</td>
            </tr>
            <tr>
              <td style={{ fontWeight: 600, color: '#60a5fa' }}>RecoveryOS Recovery Rate</td>
              <td className="font-mono" style={{ fontWeight: 700, color: '#60a5fa' }}>
                {summary.recovery_os_rate_pct}% ({formatRupees(summary.recovery_os_recovered_rupees)})
              </td>
              <td style={{ color: 'var(--text-muted)' }}>Measured outcome across batch</td>
            </tr>
            <tr style={{ background: 'rgba(16, 185, 129, 0.06)' }}>
              <td style={{ fontWeight: 700, color: '#34d399' }}>Incremental Recovery (AI Delta)</td>
              <td className="font-mono" style={{ fontWeight: 800, color: '#34d399', fontSize: '1rem' }}>
                {summary.incremental_rate_pct}% ({formatRupees(summary.incremental_ai_delta_rupees)})
              </td>
              <td style={{ fontWeight: 600, color: '#34d399' }}>The headline figure proving true agent contribution</td>
            </tr>
            <tr>
              <td style={{ fontWeight: 600, color: 'var(--text-primary)' }}>Cost of All Interventions</td>
              <td className="font-mono" style={{ fontWeight: 700 }}>{formatRupees(summary.total_intervention_cost_rupees)}</td>
              <td style={{ color: 'var(--text-muted)' }}>Sum of per-action costs (Silent ₹0, WhatsApp ₹5, Voice ₹25, Human ₹250)</td>
            </tr>
            <tr style={{ background: 'rgba(139, 92, 246, 0.06)' }}>
              <td style={{ fontWeight: 700, color: '#c084fc' }}>Net Revenue Gain & ROI</td>
              <td className="font-mono" style={{ fontWeight: 800, color: '#c084fc', fontSize: '1rem' }}>
                {formatRupees(summary.net_revenue_gain_rupees)} ({summary.roi_pct > 0 ? `${summary.roi_pct}% ROI` : 'Max ROI'})
              </td>
              <td style={{ fontWeight: 600, color: '#c084fc' }}>Incremental recovery minus intervention costs</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}
