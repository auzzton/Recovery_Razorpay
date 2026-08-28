import React, { useState, useEffect } from 'react';
import Header from './components/Header';
import HeroMetrics from './components/HeroMetrics';
import CounterfactualPanel from './components/CounterfactualPanel';
import WorkflowTable from './components/WorkflowTable';
import AuditDrawer from './components/AuditDrawer';
import ReplySimulator from './components/ReplySimulator';

export default function App() {
  const [merchants, setMerchants] = useState([]);
  const [selectedMerchant, setSelectedMerchant] = useState('ALL');
  const [summary, setSummary] = useState(null);
  const [workflows, setWorkflows] = useState([]);
  const [selectedState, setSelectedState] = useState('ALL');
  const [search, setSearch] = useState('');
  const [activeAuditWfId, setActiveAuditWfId] = useState(null);
  const [loading, setLoading] = useState(false);

  const fetchMerchants = async () => {
    try {
      const res = await fetch('/api/merchants');
      const data = await res.json();
      setMerchants(data);
    } catch (err) {
      console.error('Failed to fetch merchants:', err);
    }
  };

  const fetchSummary = async () => {
    try {
      const url = selectedMerchant && selectedMerchant !== 'ALL'
        ? `/api/dashboard/summary?merchant_id=${selectedMerchant}`
        : '/api/dashboard/summary';
      const res = await fetch(url);
      const data = await res.json();
      setSummary(data);
    } catch (err) {
      console.error('Failed to fetch summary:', err);
    }
  };

  const fetchWorkflows = async () => {
    try {
      let url = `/api/dashboard/workflows?merchant_id=${selectedMerchant}&state=${selectedState}`;
      if (search) {
        url += `&search=${encodeURIComponent(search)}`;
      }
      const res = await fetch(url);
      const data = await res.json();
      setWorkflows(data);
    } catch (err) {
      console.error('Failed to fetch workflows:', err);
    }
  };

  useEffect(() => {
    fetchMerchants();
  }, []);

  useEffect(() => {
    fetchSummary();
    fetchWorkflows();
  }, [selectedMerchant, selectedState, search]);

  const handleReSeed = async () => {
    setLoading(true);
    try {
      await fetch('/api/seed', { method: 'POST' });
      await fetchMerchants();
      await fetchSummary();
      await fetchWorkflows();
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ maxWidth: '1400px', margin: '0 auto', padding: '24px 16px' }}>
      <Header 
        merchants={merchants}
        selectedMerchant={selectedMerchant}
        onSelectMerchant={setSelectedMerchant}
        onReSeed={handleReSeed}
        isLoading={loading}
      />

      <HeroMetrics summary={summary} />

      <CounterfactualPanel summary={summary} />

      <ReplySimulator 
        workflows={workflows}
        onRefresh={() => { fetchSummary(); fetchWorkflows(); }}
      />

      <WorkflowTable 
        workflows={workflows}
        selectedState={selectedState}
        onSelectState={setSelectedState}
        search={search}
        onSearchChange={setSearch}
        onOpenAudit={(id) => setActiveAuditWfId(id)}
      />

      {activeAuditWfId && (
        <AuditDrawer 
          workflowId={activeAuditWfId}
          onClose={() => setActiveAuditWfId(null)}
        />
      )}
    </div>
  );
}
