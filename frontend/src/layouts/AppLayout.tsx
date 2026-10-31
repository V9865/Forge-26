/**
 * AppLayout — root layout: top bar + map + side panels.
 *
 * Responsive behavior:
 * - Desktop (>= 1024px): Dual docked sidebars (Intel & Sim on left, Results & Agent on right).
 * - Tablet & Mobile (< 1024px): Map occupies 100% of the viewport. Panels are accessible
 *   via responsive slide-over drawers with touch-friendly header and bottom bar toggles.
 * - Prevents horizontal overflow across all viewports down to 390px.
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { TopBar } from '@/layouts/TopBar';
import { MapWorkspace } from '@/map/MapWorkspace';
import { Panel } from '@/components/Panel';
import { FireIntelligencePanel } from '@/features/FireIntelligencePanel';
import { SimulationPanel } from '@/features/SimulationPanel';
import { AgentPanel } from '@/features/AgentPanel';
import { useJobPoller } from '@/hooks/useJobPoller';
import { getClusters, postPlan, ApiClientError } from '@/api/client';
import type {
  AOIModel,
  ClusterItem,
  OperatingMode,
  PlanRequest,
  SimulationResolution,
} from '@/types';

/**
 * Derives a safe scenario AOI conforming to backend rules:
 * - width > 0, height > 0
 * - width <= 0.6, height <= 0.6
 * - ignition point is strictly within [west, east] and [south, north]
 */
function getScenarioAoi(
  ignition: { lat: number; lng: number },
  viewport?: AOIModel | null,
): AOIModel {
  const TARGET_EXTENT = 0.45;

  if (viewport) {
    const width = viewport.east - viewport.west;
    const height = viewport.north - viewport.south;
    const containsIgnition =
      ignition.lng >= viewport.west &&
      ignition.lng <= viewport.east &&
      ignition.lat >= viewport.south &&
      ignition.lat <= viewport.north;

    if (
      width >= 0.02 &&
      width <= 0.55 &&
      height >= 0.02 &&
      height <= 0.55 &&
      containsIgnition
    ) {
      return {
        west: Number(viewport.west.toFixed(4)),
        south: Number(viewport.south.toFixed(4)),
        east: Number(viewport.east.toFixed(4)),
        north: Number(viewport.north.toFixed(4)),
      };
    }
  }

  const half = TARGET_EXTENT / 2;
  return {
    west: Number(Math.max(-180, ignition.lng - half).toFixed(4)),
    south: Number(Math.max(-90, ignition.lat - half).toFixed(4)),
    east: Number(Math.min(180, ignition.lng + half).toFixed(4)),
    north: Number(Math.min(90, ignition.lat + half).toFixed(4)),
  };
}

export function AppLayout() {
  const [operatingMode, setOperatingMode] = useState<OperatingMode>('LIVE');
  const [resolution, setResolution] = useState<SimulationResolution>(90);
  const [currentJobId, setCurrentJobId] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submissionError, setSubmissionError] = useState<string | null>(null);

  // Clusters state (GET /api/clusters)
  const [clusters, setClusters] = useState<ClusterItem[]>([]);
  const [selectedClusterId, setSelectedClusterId] = useState<string | null>(null);
  const [isLoadingClusters, setIsLoadingClusters] = useState(true);
  const [clustersError, setClustersError] = useState<string | null>(null);

  // Scenario ignition & AOI state
  const [scenarioIgnition, setScenarioIgnition] = useState<{ lat: number; lng: number } | null>(null);
  const [viewportBounds, setViewportBounds] = useState<AOIModel | null>(null);
  const [focusAoi, setFocusAoi] = useState<AOIModel | null>(null);

  // Wind override state
  const [isWindOverrideEnabled, setIsWindOverrideEnabled] = useState(false);
  const [windSpeed, setWindSpeed] = useState(7.0);
  const [windDirFrom, setWindDirFrom] = useState(240.0);

  // Evacuation & Monitoring states
  const [selectedSettlementId, setSelectedSettlementId] = useState<string | null>(null);
  const [isMonitoring, setIsMonitoring] = useState(false);

  // Responsive drawer state for screens below 1024px
  const [activeDrawer, setActiveDrawer] = useState<'left' | 'right' | null>(null);

  // Real job polling hook
  const { data: jobData } = useJobPoller(currentJobId);

  // Active cluster lookup
  const selectedCluster = useMemo(
    () => clusters.find((c) => c.id === selectedClusterId) ?? null,
    [clusters, selectedClusterId],
  );

  // Derived scenario AOI
  const scenarioAoi = useMemo(
    () => (scenarioIgnition ? getScenarioAoi(scenarioIgnition, viewportBounds) : null),
    [scenarioIgnition, viewportBounds],
  );

  // Fetch active clusters from NASA FIRMS backend
  const fetchClusters = useCallback(async () => {
    setIsLoadingClusters(true);
    setClustersError(null);
    try {
      const items = await getClusters(24);
      setClusters(items);
      // Auto-select first cluster if none is selected
      if (items.length > 0 && !selectedClusterId) {
        setSelectedClusterId(items[0].id);
        setFocusAoi(items[0].suggested_aoi);
      }
    } catch (err) {
      const message =
        err instanceof ApiClientError
          ? err.message
          : 'Could not fetch active fire clusters from backend.';
      setClustersError(message);
    } finally {
      setIsLoadingClusters(false);
    }
  }, [selectedClusterId]);

  useEffect(() => {
    const timer = setTimeout(() => {
      void fetchClusters();
    }, 0);
    return () => clearTimeout(timer);
  }, [fetchClusters]);

  // Handle cluster selection from FireIntelligencePanel
  const handleSelectCluster = (cluster: ClusterItem | null) => {
    if (cluster) {
      setSelectedClusterId(cluster.id);
      setFocusAoi(cluster.suggested_aoi);
    } else {
      setSelectedClusterId(null);
      setFocusAoi(null);
    }
  };

  // Determine submission readiness
  const isRunning =
    jobData?.status === 'queued' || jobData?.status === 'running';

  const canSubmit =
    !isRunning &&
    !isSubmitting &&
    (operatingMode === 'LIVE'
      ? selectedClusterId !== null
      : scenarioIgnition !== null);

  // Real plan submission
  const handleSubmit = async () => {
    if (!canSubmit) return;

    setIsSubmitting(true);
    setSubmissionError(null);

    try {
      let aoi: AOIModel;
      if (operatingMode === 'LIVE') {
        if (!selectedCluster) {
          throw new Error('Please select an active fire cluster to set the simulation boundary.');
        }
        aoi = selectedCluster.suggested_aoi;
      } else {
        if (!scenarioIgnition) {
          throw new Error('Please click on the map to set a scenario ignition point.');
        }
        aoi = getScenarioAoi(scenarioIgnition, viewportBounds);
      }

      const payload: PlanRequest = {
        aoi,
        mode: operatingMode,
        resolution_m: resolution,
        ...(operatingMode === 'SCENARIO' && scenarioIgnition
          ? { ignition: { lat: scenarioIgnition.lat, lon: scenarioIgnition.lng } }
          : { ignition: null }),
        ...(isWindOverrideEnabled
          ? { wind_override: { speed_ms: windSpeed, dir_from_deg: windDirFrom } }
          : { wind_override: null }),
      };

      const res = await postPlan(payload);
      setCurrentJobId(res.job_id);
    } catch (err) {
      const message =
        err instanceof ApiClientError
          ? err.message
          : (err as Error).message || 'Failed to submit simulation job.';
      setSubmissionError(message);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleModeToggle = () => {
    if (isSubmitting || isRunning) return;
    setOperatingMode((m) => {
      const next = m === 'LIVE' ? 'SCENARIO' : 'LIVE';
      if (next === 'LIVE') {
        setScenarioIgnition(null);
      }
      return next;
    });
  };

  const handleModeChange = (mode: OperatingMode) => {
    if (isSubmitting || isRunning) return;
    if (mode === 'LIVE') {
      setScenarioIgnition(null);
    }
    setOperatingMode(mode);
  };

  const handleClearIgnition = () => {
    setScenarioIgnition(null);
  };

  const handleBoundsChange = useCallback((bounds: AOIModel) => {
    setViewportBounds(bounds);
  }, []);

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
      <FireIntelligencePanel
        clusters={clusters}
        selectedClusterId={selectedClusterId}
        onSelectCluster={handleSelectCluster}
        isLoading={isLoadingClusters}
        error={clustersError}
        onRefresh={fetchClusters}
        detectionCount={selectedCluster?.count}
      />
      <SimulationPanel
        mode={operatingMode}
        onModeChange={handleModeChange}
        resolution={resolution}
        onResolutionChange={setResolution}
        selectedCluster={selectedCluster}
        scenarioIgnition={scenarioIgnition}
        scenarioAoi={scenarioAoi}
        onClearIgnition={handleClearIgnition}
        isWindOverrideEnabled={isWindOverrideEnabled}
        onToggleWindOverride={setIsWindOverrideEnabled}
        windSpeed={windSpeed}
        onWindSpeedChange={setWindSpeed}
        windDirFrom={windDirFrom}
        onWindDirFromChange={setWindDirFrom}
        canSubmit={canSubmit}
        onSubmit={handleSubmit}
        isSubmitting={isSubmitting}
        submissionError={submissionError}
        onDismissError={() => setSubmissionError(null)}
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
        modeToggleDisabled={isSubmitting || isRunning}
        jobStatus={jobData?.status ?? null}
        jobStage={jobData?.stage}
        isMonitoring={isMonitoring}
        windOverrideActive={isWindOverrideEnabled}
        selectedArea={selectedCluster ? `Cluster: ${selectedCluster.id.toUpperCase()}` : undefined}
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
            focusAoi={focusAoi}
            onBoundsChange={handleBoundsChange}
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
          aria-label="Mobile fire intelligence and simulation drawer"
        >
          <div className="flex items-center justify-between p-3 border-b border-[#162733]">
            <span className="text-xs font-bold uppercase tracking-wider text-[#e6edf3]">
              Intel & Simulation
            </span>
            <button
              onClick={closeDrawers}
              className="text-[#8b98a9] hover:text-[#e6edf3] text-sm p-1"
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
          aria-label="Mobile agent and evacuation routes drawer"
        >
          <div className="flex items-center justify-between p-3 border-b border-[#162733]">
            <span className="text-xs font-bold uppercase tracking-wider text-[#e6edf3]">
              Agent & Routes
            </span>
            <button
              onClick={closeDrawers}
              className="text-[#8b98a9] hover:text-[#e6edf3] text-sm p-1"
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
