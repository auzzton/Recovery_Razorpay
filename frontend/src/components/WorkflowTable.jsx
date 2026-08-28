import React, { useState } from 'react';
import { Search, Filter, Eye, AlertCircle, CheckCircle, Clock, Ban, UserCheck } from 'lucide-react';

export default function WorkflowTable({ workflows, selectedState, onSelectState, onOpenAudit, search, onSearchChange }) {
  const formatRupees = (cents) => {
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR',
      maximumFractionDigits: 0
    }).format((cents || 0) / 100);
  };

  const getStatusBadge = (state) => {
    switch (state) {
      case 'RECOVERED':
        return <span className="badge badge-recovered"><CheckCircle size={12} /> Recovered</span>;
      case 'PROMISE_TO_PAY':
        return <span className="badge badge-promise"><Clock size={12} /> Promise to Pay</span>;
      case 'PROMISE_BREACHED':
        return <span className="badge badge-dnc"><AlertCircle size={12} /> Promise Breached</span>;
      case 'DNC_LOCKED':
        return <span className="badge badge-dnc"><Ban size={12} /> DNC Locked</span>;
      case 'ESCALATED':
        return <span className="badge badge-escalated"><UserCheck size={12} /> Escalated</span>;
      default:
        return <span className="badge badge-triaged">{state}</span>;
    }
  };

  return (
    <div className="glass-panel" style={{ padding: '24px', borderRadius: '16px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '16px', marginBottom: '20px' }}>
        <h3 style={{ fontSize: '1.1rem', fontWeight: 700 }}>
          Ingested Event Workflows & FSM State Machine ({workflows.length})
        </h3>

        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
          {/* Search Box */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', background: 'rgba(255, 255, 255, 0.05)', padding: '6px 12px', borderRadius: '10px', border: '1px solid var(--border-card)' }}>
            <Search size={14} color="var(--text-muted)" />
            <input 
              type="text"
              placeholder="Search customer, phone, code..."
              value={search}
              onChange={(e) => onSearchChange(e.target.value)}
              style={{ background: 'transparent', border: 'none', outline: 'none', color: '#fff', fontSize: '0.85rem', width: '180px' }}
            />
          </div>

          {/* FSM State Filter Dropdown */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', background: 'rgba(255, 255, 255, 0.05)', padding: '6px 12px', borderRadius: '10px', border: '1px solid var(--border-card)' }}>
            <Filter size={14} color="var(--text-muted)" />
            <select 
              value={selectedState} 
              onChange={(e) => onSelectState(e.target.value)}
              style={{ background: 'transparent', border: 'none', outline: 'none', color: '#fff', fontSize: '0.85rem', fontWeight: 600, cursor: 'pointer' }}
            >
              <option value="ALL" style={{ background: '#121824' }}>All FSM States</option>
              <option value="TRIAGED" style={{ background: '#121824' }}>TRIAGED</option>
              <option value="RETRY_SCHEDULED" style={{ background: '#121824' }}>RETRY_SCHEDULED</option>
              <option value="AWAITING_REPLY" style={{ background: '#121824' }}>AWAITING_REPLY</option>
              <option value="PROMISE_TO_PAY" style={{ background: '#121824' }}>PROMISE_TO_PAY</option>
              <option value="PROMISE_BREACHED" style={{ background: '#121824' }}>PROMISE_BREACHED</option>
              <option value="ESCALATED" style={{ background: '#121824' }}>ESCALATED</option>
              <option value="RECOVERED" style={{ background: '#121824' }}>RECOVERED</option>
              <option value="DNC_LOCKED" style={{ background: '#121824' }}>DNC_LOCKED</option>
            </select>
          </div>
        </div>
      </div>

      <div style={{ overflowX: 'auto' }}>
        <table>
          <thead>
            <tr>
              <th>Customer</th>
              <th>Merchant</th>
              <th>Failure Code</th>
              <th>Amount</th>
              <th>FSM State</th>
              <th>Action</th>
              <th>P(Rec) / E[Val]</th>
              <th>Audit Trail</th>
            </tr>
          </thead>
          <tbody>
            {workflows.map((wf) => (
              <tr key={wf.workflow_id}>
                <td>
                  <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{wf.customer_name}</div>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                    {wf.customer_tier} • {wf.customer_phone}
                  </div>
                </td>
                <td className="font-mono" style={{ fontSize: '0.8rem', color: '#94a3b8' }}>{wf.merchant_id}</td>
                <td>
                  <span className="font-mono" style={{ fontSize: '0.8rem', background: 'rgba(255, 255, 255, 0.05)', padding: '2px 8px', borderRadius: '4px' }}>
                    {wf.failure_code}
                  </span>
                </td>
                <td className="font-mono" style={{ fontWeight: 700 }}>{formatRupees(wf.amount_in_cents)}</td>
                <td>{getStatusBadge(wf.current_state)}</td>
                <td>
                  <span style={{ fontSize: '0.8rem', fontWeight: 600, color: '#60a5fa' }}>
                    {wf.recommended_action || 'SILENT_RETRY'}
                  </span>
                </td>
                <td>
                  <div className="font-mono" style={{ fontSize: '0.8rem', fontWeight: 600 }}>
                    P={(wf.p_recovery * 100).toFixed(0)}%
                  </div>
                  <div className="font-mono" style={{ fontSize: '0.75rem', color: '#34d399' }}>
                    E[V]={formatRupees(wf.expected_value_cents)}
                  </div>
                </td>
                <td>
                  <button 
                    className="btn-secondary"
                    onClick={() => onOpenAudit(wf.workflow_id)}
                    style={{ padding: '4px 10px', fontSize: '0.75rem' }}
                  >
                    <Eye size={12} /> Inspect
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
