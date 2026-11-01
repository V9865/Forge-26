/**
 * AppLayout — root layout: top bar + map + side panels.
 *
 * Responsive behavior:
 * - Desktop (>= 1024px): Dual docked sidebars (Intel & Sim on left, Results & Agent on right).
 * - Tablet & Mobile (< 1024px): Map occupies 100% of the viewport. Panels are accessible
 *   via responsive slide-over drawers with touch-friendly header and bottom bar toggles.
 * - Prevents horizontal overflow across all viewports down to 390px.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { TopBar } from '@/layouts/TopBar';
import { MapWorkspace } from '@/map/MapWorkspace';
import { FireIntelligencePanel } from '@/features/FireIntelligencePanel';
import { SimulationPanel } from '@/features/SimulationPanel';
import { AgentPanel } from '@/features/AgentPanel';
import { SettlementsPanel } from '@/features/SettlementsPanel';
import { MetricsSummary } from '@/features/MetricsSummary';
import { EvacuationRoutesPanel } from '@/features/EvacuationRoutesPanel';
import { BriefingPanel } from '@/features/BriefingPanel';
import { ProvenancePanel } from '@/features/ProvenancePanel';
import { ValidationPanel } from '@/features/ValidationPanel';
import { useJobPoller } from '@/hooks/useJobPoller';
import { useMonitor } from '@/hooks/useMonitor';
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
  const [jobSource, setJobSource] = useState<'MANUAL' | 'MONITOR' | null>(null);
  const [boundClusterId, setBoundClusterId] = useState<string | null>(null);

  // Monitor identity and baseline refs
  const hasHydratedBaselineRef = useRef(false);
  const lastConsumedMonitorJobIdRef = useRef<string | null>(null);
  const pendingMonitorJobIdRef = useRef<string | null>(null);

  // Real autonomous background monitor hook
  const {
    status: monitorStatus,
    isEnabled: isMonitoring,
    isLoading: isMonitorLoading,
    isToggling: isMonitorToggling,
    error: monitorError,
    enable: enableMonitor,
    disable: disableMonitor,
  } = useMonitor();

  // Unified lock condition across controls during monitor sync, run, or toggle
  const isMonitorLocked = isMonitorLoading || isMonitoring || isMonitorToggling;

  const monitorLockReason = useMemo(() => {
    if (isMonitorLoading) {
      return 'Synchronizing autonomous monitor state with backend…';
    }
    if (isMonitorToggling) {
      return 'Updating autonomous monitor state…';
    }
    if (isMonitoring) {
      return 'Monitoring is bound to the AOI selected at activation. Stop monitoring before changing the target area.';
    }
    return undefined;
  }, [isMonitorLoading, isMonitorToggling, isMonitoring]);

  // Responsive drawer state for screens below 1024px
  const [activeDrawer, setActiveDrawer] = useState<'left' | 'right' | null>(null);

  // Real job polling hook
  const { data: jobData } = useJobPoller(currentJobId);

  const isRunning =
    jobData?.status === 'queued' || jobData?.status === 'running';

  const isManualJobActive =
    isSubmitting || (jobSource === 'MANUAL' && isRunning);

  // Record initial monitor current_job_id on hydration as baseline; do not adopt old ID
  useEffect(() => {
    if (!isMonitorLoading && !hasHydratedBaselineRef.current) {
      hasHydratedBaselineRef.current = true;
      lastConsumedMonitorJobIdRef.current = monitorStatus?.current_job_id ?? null;
    }
  }, [isMonitorLoading, monitorStatus?.current_job_id]);

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
    if (isMonitorLocked) return;
    if (cluster) {
      setSelectedClusterId(cluster.id);
      setFocusAoi(cluster.suggested_aoi);
    } else {
      setSelectedClusterId(null);
      setFocusAoi(null);
    }
  };

  // Connect genuinely new monitor-generated jobs to result flow without repeat reloading or overwriting manual runs
  useEffect(() => {
    const monitorJobId = monitorStatus?.current_job_id;
    if (!monitorStatus?.enabled || !monitorJobId) return;

    // Reject stale or previously consumed monitor job IDs
    if (monitorJobId === lastConsumedMonitorJobIdRef.current) return;

    // Do not adopt before initial hydration baseline is established
    if (!hasHydratedBaselineRef.current) return;

    // If manual job is active or being viewed, preserve manual job and defer / ignore monitor job
    if (isManualJobActive || jobSource === 'MANUAL') {
      pendingMonitorJobIdRef.current = monitorJobId;
      return;
    }

    lastConsumedMonitorJobIdRef.current = monitorJobId;
    {
      const timer = setTimeout(() => {
        setCurrentJobId(monitorJobId);
        setJobSource('MONITOR');
      }, 0);
      return () => clearTimeout(timer);
    }
  }, [monitorStatus?.current_job_id, monitorStatus?.enabled, isManualJobActive, jobSource]);

  // Determine monitor activation readiness and limitations
  const canEnableMonitor =
    operatingMode === 'LIVE' &&
    selectedCluster !== null &&
    !isMonitorToggling &&
    !isSubmitting &&
    !(jobData?.status === 'queued' || jobData?.status === 'running');

  const enableDisabledReason = useMemo(() => {
    if (operatingMode !== 'LIVE') {
      return 'Autonomous monitoring supports LIVE mode only. Switch to LIVE mode to monitor active fire clusters.';
    }
    if (!selectedCluster) {
      return 'Please select an active fire cluster to set the monitoring boundary.';
    }
    if (isSubmitting || jobData?.status === 'queued' || jobData?.status === 'running') {
      return 'Cannot toggle monitoring while a simulation job is active.';
    }
    return undefined;
  }, [operatingMode, selectedCluster, isSubmitting, jobData?.status]);

  const handleEnableMonitor = useCallback(async () => {
    if (!canEnableMonitor || !selectedCluster) return;
    const res = await enableMonitor(selectedCluster.suggested_aoi);
    if (res) {
      setBoundClusterId(selectedCluster.id);
      setJobSource('MONITOR');
      lastConsumedMonitorJobIdRef.current = res.current_job_id ?? null;
      pendingMonitorJobIdRef.current = null;
    }
  }, [canEnableMonitor, selectedCluster, enableMonitor]);

  const handleDisableMonitor = useCallback(async () => {
    await disableMonitor();
    setBoundClusterId(null);
    pendingMonitorJobIdRef.current = null;
  }, [disableMonitor]);

  // Determine submission readiness

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
    setJobSource('MANUAL');
    setSubmissionError(null);
    setSelectedSettlementId(null);

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
      setJobSource('MANUAL');
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
    if (isSubmitting || isRunning || isMonitorLocked) return;
    setSelectedSettlementId(null);
    setOperatingMode((m) => {
      const next = m === 'LIVE' ? 'SCENARIO' : 'LIVE';
      if (next === 'LIVE') {
        setScenarioIgnition(null);
      }
      return next;
    });
  };

  const handleModeChange = (mode: OperatingMode) => {
    if (isSubmitting || isRunning || isMonitorLocked) return;
    setSelectedSettlementId(null);
    if (mode === 'LIVE') {
      setScenarioIgnition(null);
    }
    setOperatingMode(mode);
  };

  const handleClearIgnition = () => {
    setScenarioIgnition(null);
  };

  const handleSelectIgnition = (pt: { lat: number; lng: number }) => {
    setScenarioIgnition(pt);
    const derivedAoi = getScenarioAoi(pt, viewportBounds);
    setFocusAoi(derivedAoi);
  };

  const handleBoundsChange = useCallback((bounds: AOIModel) => {
    setViewportBounds(bounds);
  }, []);

  const drawerTriggerRef = useRef<HTMLElement | null>(null);
  const leftDrawerRef = useRef<HTMLElement | null>(null);
  const rightDrawerRef = useRef<HTMLElement | null>(null);
  const leftDrawerCloseBtnRef = useRef<HTMLButtonElement | null>(null);
  const rightDrawerCloseBtnRef = useRef<HTMLButtonElement | null>(null);

  const toggleLeftDrawer = () => {
    setActiveDrawer((current) => {
      if (current === 'left') {
        setTimeout(() => drawerTriggerRef.current?.focus(), 0);
        return null;
      }
      drawerTriggerRef.current = document.activeElement as HTMLElement | null;
      return 'left';
    });
  };

  const toggleRightDrawer = () => {
    setActiveDrawer((current) => {
      if (current === 'right') {
        setTimeout(() => drawerTriggerRef.current?.focus(), 0);
        return null;
      }
      drawerTriggerRef.current = document.activeElement as HTMLElement | null;
      return 'right';
    });
  };

  const closeDrawers = () => {
    setActiveDrawer(null);
    setTimeout(() => drawerTriggerRef.current?.focus(), 0);
  };

  // Initial focus management for mobile drawers
  useEffect(() => {
    if (activeDrawer === 'left') {
      const timer = setTimeout(() => {
        leftDrawerCloseBtnRef.current?.focus();
      }, 50);
      return () => clearTimeout(timer);
    } else if (activeDrawer === 'right') {
      const timer = setTimeout(() => {
        rightDrawerCloseBtnRef.current?.focus();
      }, 50);
      return () => clearTimeout(timer);
    }
  }, [activeDrawer]);

  // Focus containment (trap) and Escape key handling for mobile drawers
  useEffect(() => {
    if (activeDrawer === null) return;

    const container = activeDrawer === 'left' ? leftDrawerRef.current : rightDrawerRef.current;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        closeDrawers();
        return;
      }

      if (e.key === 'Tab' && container) {
        const focusableElements = container.querySelectorAll<HTMLElement>(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
        );
        const focusables = Array.from(focusableElements).filter(
          (el) => !el.hasAttribute('disabled') && el.getAttribute('aria-hidden') !== 'true'
        );

        if (focusables.length === 0) return;

        const firstElement = focusables[0];
        const lastElement = focusables[focusables.length - 1];

        if (e.shiftKey) {
          if (document.activeElement === firstElement || !container.contains(document.activeElement)) {
            e.preventDefault();
            lastElement.focus();
          }
        } else {
          if (document.activeElement === lastElement || !container.contains(document.activeElement)) {
            e.preventDefault();
            firstElement.focus();
          }
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [activeDrawer]);

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
        isLocked={isMonitorLocked}
        lockReason={monitorLockReason}
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
        onSelectIgnition={handleSelectIgnition}
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
        isModeLocked={isMonitorLocked}
        modeLockedReason={monitorLockReason}
      />
    </>
  );

  // Content for the right panels (Agent & Results)
  const rightPanelsContent = (
    <>
      <BriefingPanel
        briefing={jobData?.result?.briefing ?? null}
        warnings={jobData?.result?.warnings ?? []}
        jobStatus={jobData?.status ?? null}
      />

      <MetricsSummary metrics={jobData?.result?.metrics ?? null} />

      <SettlementsPanel
        settlements={jobData?.result?.settlements ?? null}
        routes={jobData?.result?.routes ?? null}
        naiveCutSegments={jobData?.result?.naive_cut_segments ?? null}
        selectedSettlementId={selectedSettlementId}
        onSelectSettlement={setSelectedSettlementId}
        jobStatus={jobData?.status ?? null}
      />

      <EvacuationRoutesPanel
        settlements={jobData?.result?.settlements ?? null}
        routes={jobData?.result?.routes ?? null}
        naiveCutSegments={jobData?.result?.naive_cut_segments ?? null}
        selectedSettlementId={selectedSettlementId}
        onSelectSettlement={setSelectedSettlementId}
        jobStatus={jobData?.status ?? null}
      />

      <ProvenancePanel
        provenance={jobData?.result?.provenance ?? null}
        jobStatus={jobData?.status ?? null}
      />

      <ValidationPanel />

      <AgentPanel

        monitorStatus={monitorStatus}
        isMonitorLoading={isMonitorLoading}
        isMonitorToggling={isMonitorToggling}
        monitorError={monitorError}
        onEnableMonitor={handleEnableMonitor}
        onDisableMonitor={handleDisableMonitor}
        canEnableMonitor={canEnableMonitor}
        enableDisabledReason={enableDisabledReason}
        monitoredClusterId={boundClusterId}
        currentJobId={currentJobId}
        jobSource={jobSource}
        currentStage={jobData?.stage ?? undefined}
        trace={jobData?.trace ?? jobData?.result?.trace ?? []}
      />
    </>
  );

  return (
    <div className="flex flex-col h-full w-full overflow-hidden bg-[#0b0f14]">
      {/* Top status bar */}
      <TopBar
        operatingMode={operatingMode}
        onModeToggle={handleModeToggle}
        modeToggleDisabled={isSubmitting || isRunning || isMonitorLocked}
        isMonitorLocked={isMonitorLocked}
        monitorLockReason={monitorLockReason}
        isMonitoring={isMonitoring}
        jobStatus={jobData?.status ?? null}
        jobStage={jobData?.stage}

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
              className={`flex items-center gap-1.5 px-3.5 py-2 min-h-[40px] text-xs font-semibold rounded-full transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-[#ff6a2b] ${
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
              className={`flex items-center gap-1.5 px-3.5 py-2 min-h-[40px] text-xs font-semibold rounded-full transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-[#ff6a2b] ${
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
            className="lg:hidden fixed inset-0 bg-black/70 backdrop-blur-xs z-30 transition-opacity cursor-pointer"
            onClick={closeDrawers}
            aria-hidden="true"
          />
        )}

        {/* ── Mobile/Tablet Left Drawer (< 1024px) ──────────────── */}
        <aside
          ref={leftDrawerRef}
          id="mobile-left-drawer"
          role="dialog"
          aria-modal="true"
          aria-labelledby="mobile-left-drawer-title"
          className={`lg:hidden fixed inset-y-0 left-0 z-40 w-72 sm:w-80 max-w-[85vw] bg-[#0b0f14] border-r border-[#162733] shadow-2xl flex flex-col transition-transform duration-200 ease-out ${
            activeDrawer === 'left' ? 'translate-x-0' : '-translate-x-full'
          }`}
          aria-label="Mobile fire intelligence and simulation drawer"
        >
          <div className="flex items-center justify-between p-3 border-b border-[#162733]">
            <span id="mobile-left-drawer-title" className="text-xs font-bold uppercase tracking-wider text-[#e6edf3]">
              Intel & Simulation
            </span>
            <button
              ref={leftDrawerCloseBtnRef}
              onClick={closeDrawers}
              className="text-[#8b98a9] hover:text-[#e6edf3] text-sm w-8 h-8 flex items-center justify-center rounded focus:outline-none focus-visible:ring-2 focus-visible:ring-[#ff6a2b]"
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
          ref={rightDrawerRef}
          id="mobile-right-drawer"
          role="dialog"
          aria-modal="true"
          aria-labelledby="mobile-right-drawer-title"
          className={`lg:hidden fixed inset-y-0 right-0 z-40 w-72 sm:w-80 max-w-[85vw] bg-[#0b0f14] border-l border-[#162733] shadow-2xl flex flex-col transition-transform duration-200 ease-out ${
            activeDrawer === 'right' ? 'translate-x-0' : 'translate-x-full'
          }`}
          aria-label="Mobile agent and evacuation routes drawer"
        >
          <div className="flex items-center justify-between p-3 border-b border-[#162733]">
            <span id="mobile-right-drawer-title" className="text-xs font-bold uppercase tracking-wider text-[#e6edf3]">
              Agent & Routes
            </span>
            <button
              ref={rightDrawerCloseBtnRef}
              onClick={closeDrawers}
              className="text-[#8b98a9] hover:text-[#e6edf3] text-sm w-8 h-8 flex items-center justify-center rounded focus:outline-none focus-visible:ring-2 focus-visible:ring-[#ff6a2b]"
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
