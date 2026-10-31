/**
 * AppLayout — root layout: top bar + map + side panels.
 *
 * Responsive behavior:
 * - Desktop (>= 1024px): Dual docked sidebars (Intel & Sim on left, Results & Agent on right).
 * - Tablet & Mobile (< 1024px): Map occupies 100% of the viewport. Panels are accessible
 *   via responsive slide-over drawers with touch-friendly header and bottom bar toggles.
 * - Prevents horizontal overflow across all viewports down to 390px.
 */

import { useState } from 'react';
import { TopBar } from '@/layouts/TopBar';
import { MapWorkspace } from '@/map/MapWorkspace';
import { Panel } from '@/components/Panel';
import { FireIntelligencePanel } from '@/features/FireIntelligencePanel';
import { SimulationPanel } from '@/features/SimulationPanel';
import { AgentPanel } from '@/features/AgentPanel';
import { useJobPoller } from '@/hooks/useJobPoller';
import type { OperatingMode, SimulationResolution } from '@/types';

export function AppLayout() {
  const [operatingMode, setOperatingMode] = useState<OperatingMode>('LIVE');
  const [resolution, setResolution] = useState<SimulationResolution>(60);
  const [windOverrideActive] = useState(false);
  const [isMonitoring, setIsMonitoring] = useState(false);
  const [currentJobId] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [selectedClusterId] = useState<string | null>(null);
  const [selectedSettlementId, setSelectedSettlementId] = useState<string | null>(null);
  const [scenarioIgnition, setScenarioIgnition] = useState<{ lat: number; lng: number } | null>(null);

  // Responsive drawer state for screens below 1024px
  const [activeDrawer, setActiveDrawer] = useState<'left' | 'right' | null>(null);

  const { data: jobData } = useJobPoller(currentJobId);

  const canSubmit =
    operatingMode === 'SCENARIO' ||
    (operatingMode === 'LIVE' && selectedClusterId !== null);

  const handleSubmit = async () => {
    // F3 will implement full submission logic
    setIsSubmitting(true);
    await new Promise((r) => setTimeout(r, 500));
    setIsSubmitting(false);
  };

  const handleModeToggle = () => {
    setOperatingMode((m) => {
      const next = m === 'LIVE' ? 'SCENARIO' : 'LIVE';
      if (next === 'LIVE') {
        setScenarioIgnition(null);
      }
      return next;
    });
  };

  const handleModeChange = (mode: OperatingMode) => {
    if (mode === 'LIVE') {
      setScenarioIgnition(null);
    }
    setOperatingMode(mode);
  };

  const toggleLeftDrawer = () => {
    setActiveDrawer((current) => (current === 'left' ? null : 'left'));
  };

  const toggleRightDrawer = () => {
    setActiveDrawer((current) => (current === 'right' ? null : 'right'));
  };

  const closeDrawers = () => {
    setActiveDrawer(null);
  };

  // Content for the left panels (Intelligence & Simulation)
  const leftPanelsContent = (
    <>
      <FireIntelligencePanel />
      <SimulationPanel
        mode={operatingMode}
        onModeChange={handleModeChange}
        resolution={resolution}
        onResolutionChange={setResolution}
        canSubmit={canSubmit}
        onSubmit={handleSubmit}
        isSubmitting={isSubmitting}
        jobData={jobData}
      />
    </>
  );

  // Content for the right panels (Agent & Results)
  const rightPanelsContent = (
    <>
      <AgentPanel
        isMonitoring={isMonitoring}
        onToggleMonitoring={() => setIsMonitoring((v) => !v)}
        trace={jobData?.trace}
      />

      {/* Settlements panel using reusable Panel component */}
      <Panel title="Settlements" icon="⬡" collapsible defaultCollapsed={false}>
        <div className="p-3">
          <p className="text-xs text-[#8b98a9] leading-relaxed">
            Settlement analysis will appear here after running a simulation.
          </p>
        </div>
      </Panel>

      {/* Evacuation Routes panel using reusable Panel component */}
      <Panel title="Evacuation Routes" icon="→" collapsible defaultCollapsed={false}>
        <div className="p-3">
          <p className="text-xs text-[#8b98a9] leading-relaxed">
            Fire-aware and baseline route recommendations will appear here after simulation.
          </p>
        </div>
      </Panel>
    </>
  );

  return (
    <div className="flex flex-col h-full w-full overflow-hidden bg-[#0b0f14]">
      {/* Top status bar */}
      <TopBar
        operatingMode={operatingMode}
        onModeToggle={handleModeToggle}
        jobStatus={jobData?.status ?? null}
        jobStage={jobData?.stage}
        isMonitoring={isMonitoring}
        windOverrideActive={windOverrideActive}
        onToggleLeftDrawer={toggleLeftDrawer}
        onToggleRightDrawer={toggleRightDrawer}
        activeDrawer={activeDrawer}
      />

      {/* Main workspace */}
      <div className="relative flex flex-1 min-h-0 w-full overflow-hidden">
        {/* ── Left panel dock (Desktop >= 1024px) ───────────────── */}
        <aside
          className="hidden lg:flex w-64 xl:w-72 flex-shrink-0 flex-col gap-2 p-2 border-r border-[#162733] overflow-y-auto"
          aria-label="Fire intelligence and simulation controls"
        >
          {leftPanelsContent}
        </aside>

        {/* ── Center: Map Workspace (full width on tablet & mobile) ─ */}
        <main className="relative flex-1 flex flex-col min-h-0 min-w-0 overflow-hidden" role="main">
          <MapWorkspace
            detections={jobData?.result?.detections ?? null}
            arrivalBands={jobData?.result?.arrival_bands ?? null}
            settlements={jobData?.result?.settlements ?? null}
            routes={jobData?.result?.routes ?? null}
            naiveCutSegments={jobData?.result?.naive_cut_segments ?? null}
            selectedSettlementId={selectedSettlementId}
            onSelectSettlement={setSelectedSettlementId}
            scenarioIgnition={operatingMode === 'SCENARIO' ? scenarioIgnition : null}
            onSelectIgnition={setScenarioIgnition}
            isScenarioMode={operatingMode === 'SCENARIO'}
          />

          {/* Floating quick-access drawer pills for tablet & mobile (< 1024px) */}
          <div
            className="lg:hidden absolute bottom-3 left-1/2 -translate-x-1/2 z-10 flex items-center gap-1.5 p-1 bg-[#121821]/90 backdrop-blur-md border border-[#162733] rounded-full shadow-lg"
            role="toolbar"
            aria-label="Panel quick access"
          >
            <button
              onClick={toggleLeftDrawer}
              className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-full transition-colors ${
                activeDrawer === 'left'
                  ? 'bg-[#ff6a2b] text-white shadow'
                  : 'text-[#8b98a9] hover:text-[#e6edf3]'
              }`}
              aria-expanded={activeDrawer === 'left'}
              aria-controls="mobile-left-drawer"
            >
              <span aria-hidden="true">◉</span>
              <span>Intel & Sim</span>
            </button>
            <div className="w-px h-4 bg-[#162733]" aria-hidden="true" />
            <button
              onClick={toggleRightDrawer}
              className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-full transition-colors ${
                activeDrawer === 'right'
                  ? 'bg-[#ff6a2b] text-white shadow'
                  : 'text-[#8b98a9] hover:text-[#e6edf3]'
              }`}
              aria-expanded={activeDrawer === 'right'}
              aria-controls="mobile-right-drawer"
            >
              <span aria-hidden="true">◈</span>
              <span>Agent & Routes</span>
            </button>
          </div>
        </main>

        {/* ── Right panel dock (Desktop >= 1024px) ──────────────── */}
        <aside
          className="hidden lg:flex w-64 xl:w-72 flex-shrink-0 flex-col gap-2 p-2 border-l border-[#162733] overflow-y-auto"
          aria-label="Agent briefing and evacuation intelligence"
        >
          {rightPanelsContent}
        </aside>

        {/* ── Mobile/Tablet Backdrop (< 1024px) ─────────────────── */}
        {activeDrawer !== null && (
          <div
            className="lg:hidden fixed inset-0 bg-black/60 backdrop-blur-xs z-30 transition-opacity"
            onClick={closeDrawers}
            aria-hidden="true"
          />
        )}

        {/* ── Mobile/Tablet Left Drawer (< 1024px) ──────────────── */}
        <aside
          id="mobile-left-drawer"
          className={`lg:hidden fixed inset-y-0 left-0 z-40 w-72 sm:w-80 max-w-[85vw] bg-[#0b0f14] border-r border-[#162733] shadow-2xl flex flex-col transition-transform duration-200 ease-out ${
            activeDrawer === 'left' ? 'translate-x-0' : '-translate-x-full'
          }`}
          aria-label="Intelligence and simulation drawer"
          aria-hidden={activeDrawer !== 'left'}
        >
          <div className="flex items-center justify-between p-3 border-b border-[#162733]">
            <span className="text-xs font-bold uppercase tracking-wider text-[#e6edf3]">
              Intelligence & Simulation
            </span>
            <button
              onClick={closeDrawers}
              className="text-[#8b98a9] hover:text-[#e6edf3] p-1 rounded"
              aria-label="Close drawer"
            >
              ✕
            </button>
          </div>
          <div className="flex-1 overflow-y-auto p-2 flex flex-col gap-2">
            {leftPanelsContent}
          </div>
        </aside>

        {/* ── Mobile/Tablet Right Drawer (< 1024px) ─────────────── */}
        <aside
          id="mobile-right-drawer"
          className={`lg:hidden fixed inset-y-0 right-0 z-40 w-72 sm:w-80 max-w-[85vw] bg-[#0b0f14] border-l border-[#162733] shadow-2xl flex flex-col transition-transform duration-200 ease-out ${
            activeDrawer === 'right' ? 'translate-x-0' : 'translate-x-full'
          }`}
          aria-label="Agent and evacuation intelligence drawer"
          aria-hidden={activeDrawer !== 'right'}
        >
          <div className="flex items-center justify-between p-3 border-b border-[#162733]">
            <span className="text-xs font-bold uppercase tracking-wider text-[#e6edf3]">
              Agent & Results
            </span>
            <button
              onClick={closeDrawers}
              className="text-[#8b98a9] hover:text-[#e6edf3] p-1 rounded"
              aria-label="Close drawer"
            >
              ✕
            </button>
          </div>
          <div className="flex-1 overflow-y-auto p-2 flex flex-col gap-2">
            {rightPanelsContent}
          </div>
        </aside>
      </div>
    </div>
  );
}
