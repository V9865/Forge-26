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
import type { FlyToTarget } from '@/map/mapTypes';

/**
 * Derives a safe scenario AOI conforming to backend rules:
 * - width > 0, height > 0
 * - width <= 0.6, height <= 0.6
 * - ignition point is strictly within [west, east] and [south, north]
 */
function getScenarioAoi(ignition: { lat: number; lng: number }): AOIModel {
  // If clicked within or near the Valais benchmark corridor, snap to the exact cached corridor
  if (
    Math.abs(ignition.lat - 46.28) <= 0.12 &&
    Math.abs(ignition.lng - 7.55) <= 0.12
  ) {
    return { west: 7.45, south: 46.20, east: 7.65, north: 46.35 };
  }

  // Standard 0.20° x 0.20° extent (~20km x 15km) centered on the ignition beacon
  const half = 0.10;
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
  const [, setViewportBounds] = useState<AOIModel | null>(null);
  const [focusAoi, setFocusAoi] = useState<AOIModel | null>(null);
  const [flyToTarget, setFlyToTarget] = useState<FlyToTarget | null>(null);

  // Wind override state
  const [isWindOverrideEnabled, setIsWindOverrideEnabled] = useState(false);
  const [windSpeed, setWindSpeed] = useState(7.0);
  const [windDirFrom, setWindDirFrom] = useState(240.0);

  // Evacuation & Monitoring states
  const [selectedSettlementId, setSelectedSettlementId] = useState<string | null>(null);
  const [jobSource, setJobSource] = useState<'MANUAL' | 'MONITOR' | null>(null);
  const [boundClusterId, setBoundClusterId] = useState<string | null>(null);
  const [rightPanelMode, setRightPanelMode] = useState<'standard' | 'wide' | 'collapsed'>('wide');
  const [leftWidth, setLeftWidth] = useState<number>(340);
  const [rightWidth, setRightWidth] = useState<number>(500);
  const [isDraggingLeft, setIsDraggingLeft] = useState(false);
  const [isDraggingRight, setIsDraggingRight] = useState(false);

  useEffect(() => {
    if (!isDraggingLeft && !isDraggingRight) return;

    const handleMouseMove = (e: MouseEvent) => {
      if (isDraggingLeft) {
        setLeftWidth(Math.min(520, Math.max(260, e.clientX)));
      }
      if (isDraggingRight) {
        setRightWidth(Math.min(740, Math.max(320, window.innerWidth - e.clientX)));
      }
    };

    const handleMouseUp = () => {
      setIsDraggingLeft(false);
      setIsDraggingRight(false);
    };

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }, [isDraggingLeft, isDraggingRight]);

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
  const { data: jobData, error: jobPollError } = useJobPoller(currentJobId);

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
    () => (scenarioIgnition ? getScenarioAoi(scenarioIgnition) : null),
    [scenarioIgnition],
  );

  // Fetch active clusters from NASA FIRMS backend
  const fetchClusters = useCallback(async () => {
    setIsLoadingClusters(true);
    setClustersError(null);
    try {
      const items = await getClusters(24);
      setClusters(items);

      // Keep selection aligned with the current live FIRMS response. A cluster
      // can disappear between refreshes; never leave a stale ID selected.
      if (items.length === 0) {
        setSelectedClusterId(null);
        setFocusAoi(null);
      } else if (!selectedClusterId || !items.some((item) => item.id === selectedClusterId)) {
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

    // A report belongs to the AOI/job that produced it. Clear the previous
    // result when the operator selects a different detected cluster so an old
    // briefing is never presented as the report for the new selection.
    setCurrentJobId(null);
    setJobSource('MANUAL');
    setSelectedSettlementId(null);
    setSubmissionError(null);

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

  // Auto-focus map on simulation results when job finishes
  useEffect(() => {
    if (jobData?.status === 'done' && jobData.result?.aoi) {
      setFocusAoi(jobData.result.aoi);
    }
  }, [jobData?.status, jobData?.result?.aoi]);

  // Determine submission readiness

  const canSubmit =
    !isRunning &&
    !isSubmitting &&
    (operatingMode === 'LIVE'
      ? selectedCluster !== null
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
        aoi = getScenarioAoi(scenarioIgnition);
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
    setOperatingMode('SCENARIO');
    setScenarioIgnition(pt);
    setSubmissionError(null);
    const derivedAoi = getScenarioAoi(pt);
    setFocusAoi(derivedAoi);
  };

  const handleSelectSettlement = (id: string | null) => {
    setSelectedSettlementId(id);
    if (id && jobData?.result?.settlements?.features) {
      const feat = jobData.result.settlements.features.find((f) => f.properties?.id === id);
      if (feat && feat.geometry?.type === 'Point') {
        const [lng, lat] = feat.geometry.coordinates;
        setFlyToTarget({
          center: [lng, lat],
          zoom: 12.5,
          timestamp: Date.now(),
        });
      }
    }
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
        jobStatus={jobData?.status ?? (jobPollError ? 'error' : null)}
        jobError={jobData?.error?.message ?? jobPollError}
      />

      <MetricsSummary metrics={jobData?.result?.metrics ?? null} />

      <SettlementsPanel
        settlements={jobData?.result?.settlements ?? null}
        routes={jobData?.result?.routes ?? null}
        naiveCutSegments={jobData?.result?.naive_cut_segments ?? null}
        selectedSettlementId={selectedSettlementId}
        onSelectSettlement={handleSelectSettlement}
        jobStatus={jobData?.status ?? null}
      />

      <EvacuationRoutesPanel
        settlements={jobData?.result?.settlements ?? null}
        routes={jobData?.result?.routes ?? null}
        naiveCutSegments={jobData?.result?.naive_cut_segments ?? null}
        selectedSettlementId={selectedSettlementId}
        onSelectSettlement={handleSelectSettlement}
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
        selectedArea={
          operatingMode === 'SCENARIO'
            ? scenarioIgnition
              ? `Scenario Ignition: (${scenarioIgnition.lat.toFixed(3)}, ${scenarioIgnition.lng.toFixed(3)})`
              : 'Scenario Mode'
            : selectedCluster
            ? `Cluster: ${selectedCluster.id.toUpperCase()}${selectedCluster.name ? ` • ${selectedCluster.name}` : ''}`
            : undefined
        }
        onToggleLeftDrawer={toggleLeftDrawer}
        onToggleRightDrawer={toggleRightDrawer}
        activeDrawer={activeDrawer}
      />

      {/* Main workspace */}
      <div className="relative flex flex-1 min-h-0 w-full overflow-hidden">
        {/* ── Left panel dock (Desktop >= 1024px, Resizable) ───── */}
        <aside
          style={{ width: `${leftWidth}px` }}
          className="hidden lg:flex flex-shrink-0 flex-col gap-2 p-2 border-r border-[#162733] overflow-y-auto"
          aria-label="Fire intelligence and simulation controls"
        >
          {leftPanelsContent}
        </aside>

        {/* Left Resize Splitter Handle */}
        <div
          onMouseDown={() => setIsDraggingLeft(true)}
          className={`hidden lg:flex w-1.5 hover:w-2 bg-[#162733] hover:bg-[#ff6a2b] transition-all cursor-col-resize items-center justify-center select-none group z-10 shrink-0 ${
            isDraggingLeft ? 'w-2 bg-[#ff6a2b]' : ''
          }`}
          title="Drag to resize Intel & Sim sidebar"
        >
          <div className="w-0.5 h-6 bg-[#657787] group-hover:bg-white rounded-full transition-colors" />
        </div>

        {/* ── Center: Map Workspace (full width on tablet & mobile) ─ */}
        <main className="relative flex-1 flex flex-col min-h-0 min-w-0 overflow-hidden" role="main">
          <MapWorkspace
            detections={operatingMode === 'SCENARIO' ? null : (jobData?.result?.detections ?? null)}
            arrivalBands={jobData?.result?.arrival_bands ?? null}
            settlements={jobData?.result?.settlements ?? null}
            routes={jobData?.result?.routes ?? null}
            naiveCutSegments={jobData?.result?.naive_cut_segments ?? null}
            roads={jobData?.result?.roads ?? null}
            selectedSettlementId={selectedSettlementId}
            onSelectSettlement={handleSelectSettlement}
            scenarioIgnition={operatingMode === 'SCENARIO' ? scenarioIgnition : null}
            onSelectIgnition={handleSelectIgnition}
            isScenarioMode={operatingMode === 'SCENARIO'}
            focusAoi={focusAoi}
            onBoundsChange={handleBoundsChange}
            flyToTarget={flyToTarget}
            jobStatus={jobData?.status ?? null}
            jobError={jobData?.error ?? null}
            windData={jobData?.result?.wind ?? null}
          />

          {rightPanelMode === 'collapsed' && (
            <button
              type="button"
              onClick={() => setRightPanelMode('wide')}
              className="hidden lg:flex items-center gap-1.5 absolute top-3 right-3 z-20 px-3 py-1.5 bg-[#121821]/95 backdrop-blur-md border border-[#ff6a2b]/60 hover:border-[#ff6a2b] text-[#e6edf3] text-xs font-semibold rounded-lg shadow-xl transition-all cursor-pointer hover:bg-[#162733]"
              title="Expand Evacuation Intelligence & Agent Briefing"
            >
              <span>◀ Evac & Briefing</span>
            </button>
          )}

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

        {/* Right Resize Splitter Handle */}
        {rightPanelMode !== 'collapsed' && (
          <div
            onMouseDown={() => setIsDraggingRight(true)}
            className={`hidden lg:flex w-1.5 hover:w-2 bg-[#162733] hover:bg-[#ff6a2b] transition-all cursor-col-resize items-center justify-center select-none group z-10 shrink-0 ${
              isDraggingRight ? 'w-2 bg-[#ff6a2b]' : ''
            }`}
            title="Drag to resize Evacuation & Briefing sidebar"
          >
            <div className="w-0.5 h-6 bg-[#657787] group-hover:bg-white rounded-full transition-colors" />
          </div>
        )}

        {/* ── Right panel dock (Desktop >= 1024px, Resizable) ───── */}
        {rightPanelMode !== 'collapsed' && (
          <aside
            style={{ width: `${rightWidth}px` }}
            className="hidden lg:flex flex-shrink-0 flex-col gap-2 p-2 border-l border-[#162733] overflow-y-auto"
            aria-label="Agent briefing and evacuation intelligence"
          >
            {/* Header Bar with Width Presets and Collapse controls */}
            <div className="flex items-center justify-between px-2.5 py-1.5 bg-[#090d12] border border-[#162733] rounded-lg shrink-0">
              <div className="flex items-center gap-1.5">
                <span className="text-xs">📋</span>
                <span className="text-[11px] font-bold uppercase tracking-wider text-[#e6edf3]">
                  Intelligence & Evac
                </span>
                <span className="text-[10px] text-[#8b98a9] font-mono">({rightWidth}px)</span>
              </div>
              <div className="flex items-center gap-1">
                <button
                  type="button"
                  onClick={() => setRightWidth(360)}
                  className={`px-1.5 py-0.5 text-[10px] font-medium rounded transition-colors cursor-pointer ${
                    rightWidth <= 400 ? 'bg-[#ff6a2b] text-white' : 'text-[#8b98a9] hover:text-[#e6edf3] bg-[#121821] border border-[#162733]'
                  }`}
                  title="360px Compact View"
                >
                  360px
                </button>
                <button
                  type="button"
                  onClick={() => setRightWidth(520)}
                  className={`px-1.5 py-0.5 text-[10px] font-medium rounded transition-colors cursor-pointer ${
                    rightWidth > 400 && rightWidth <= 580 ? 'bg-[#ff6a2b] text-white' : 'text-[#8b98a9] hover:text-[#e6edf3] bg-[#121821] border border-[#162733]'
                  }`}
                  title="520px Wide View"
                >
                  520px
                </button>
                <button
                  type="button"
                  onClick={() => setRightWidth(660)}
                  className={`px-1.5 py-0.5 text-[10px] font-medium rounded transition-colors cursor-pointer ${
                    rightWidth > 580 ? 'bg-[#ff6a2b] text-white' : 'text-[#8b98a9] hover:text-[#e6edf3] bg-[#121821] border border-[#162733]'
                  }`}
                  title="660px Extra-Wide View"
                >
                  660px
                </button>
                <button
                  type="button"
                  onClick={() => setRightPanelMode('collapsed')}
                  className="w-6 h-5 flex items-center justify-center text-[11px] text-[#8b98a9] hover:text-[#ff3b30] bg-[#121821] hover:bg-[#162733] border border-[#162733] rounded transition-colors cursor-pointer ml-1"
                  title="Collapse sidebar for full-screen map"
                  aria-label="Collapse panel"
                >
                  ✕
                </button>
              </div>
            </div>

            {rightPanelsContent}
          </aside>
        )}

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
          className={`lg:hidden fixed inset-y-0 left-0 z-40 w-84 sm:w-96 max-w-[92vw] bg-[#0b0f14] border-r border-[#162733] shadow-2xl flex flex-col transition-transform duration-200 ease-out ${
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
