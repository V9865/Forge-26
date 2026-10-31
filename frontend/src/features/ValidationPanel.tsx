/**
 * ValidationPanel — Displays empirical model validation against historical satellite
 * observations and engineering physical assumptions underpinning EmberRoute.
 *
 * Requirements:
 * - Clear disclaimer stating this is historical model validation, not operational certification.
 * - Converts recall fractions to percentages only for display without mutating raw values.
 * - Shows an honest empty/unavailable state if /api/assumptions is blank or not found.
 */

import { useEffect, useState } from 'react';
import { Panel } from '@/components/Panel';
import { getAssumptions, getValidation, ApiClientError } from '@/api/client';
import type { ValidationResponse } from '@/types';

type Tab = 'validation' | 'assumptions';

export function ValidationPanel() {
  const [activeTab, setActiveTab] = useState<Tab>('validation');

  // Empirical validation state
  const [validationData, setValidationData] = useState<ValidationResponse | null>(null);
  const [isValidatingLoading, setIsValidationLoading] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);

  // Assumptions state
  const [assumptionsText, setAssumptionsText] = useState<string | null>(null);
  const [isAssumptionsLoading, setIsAssumptionsLoading] = useState(false);
  const [assumptionsError, setAssumptionsError] = useState<string | null>(null);

  // Fetch validation data
  useEffect(() => {
    let mounted = true;
    const fetchVal = async () => {
      setIsValidationLoading(true);
      setValidationError(null);
      try {
        const res = await getValidation();
        if (mounted) setValidationData(res);
      } catch (err) {
        if (mounted) {
          setValidationError(
            err instanceof ApiClientError ? err.message : 'Failed to load validation dataset.',
          );
        }
      } finally {
        if (mounted) setIsValidationLoading(false);
      }
    };

    void fetchVal();
    return () => {
      mounted = false;
    };
  }, []);

  // Fetch assumptions data
  useEffect(() => {
    let mounted = true;
    const fetchAssump = async () => {
      setIsAssumptionsLoading(true);
      setAssumptionsError(null);
      try {
        const res = await getAssumptions();
        if (mounted) setAssumptionsText(res.text);
      } catch (err) {
        if (mounted) {
          setAssumptionsError(
            err instanceof ApiClientError ? err.message : 'Failed to load assumptions document.',
          );
        }
      } finally {
        if (mounted) setIsAssumptionsLoading(false);
      }
    };

    void fetchAssump();
    return () => {
      mounted = false;
    };
  }, []);

  // Check if assumptions text is empty, whitespace only, or default not-found message
  const hasValidAssumptions =
    Boolean(assumptionsText && assumptionsText.trim().length > 0) &&
    assumptionsText?.trim() !== 'Assumptions documentation not found.';

  return (
    <Panel title="Model Validation & Assumptions" icon="⚖" collapsible defaultCollapsed>
      {/* Sub-tabs header */}
      <div className="flex border-b border-[#162733] bg-[#090d12]">
        <button
          onClick={() => setActiveTab('validation')}
          className={`flex-1 py-1.5 text-[11px] font-semibold text-center border-b-2 transition-colors ${
            activeTab === 'validation'
              ? 'border-[#ff6a2b] text-[#e6edf3]'
              : 'border-transparent text-[#8b98a9] hover:text-[#e6edf3]'
          }`}
          aria-selected={activeTab === 'validation'}
        >
          Empirical Validation
        </button>
        <button
          onClick={() => setActiveTab('assumptions')}
          className={`flex-1 py-1.5 text-[11px] font-semibold text-center border-b-2 transition-colors ${
            activeTab === 'assumptions'
              ? 'border-[#ff6a2b] text-[#e6edf3]'
              : 'border-transparent text-[#8b98a9] hover:text-[#e6edf3]'
          }`}
          aria-selected={activeTab === 'assumptions'}
        >
          Model Assumptions
        </button>
      </div>

      <div className="p-3">
        {/* ─── TAB 1: Empirical Validation ───────────────────────────────── */}
        {activeTab === 'validation' && (
          <div className="flex flex-col gap-3">
            {/* Mandatory Historical Validation Disclaimer */}
            <div className="p-2.5 rounded bg-[#162733]/40 border border-[#162733] text-[10px] text-[#8b98a9] leading-relaxed">
              <span className="font-semibold text-[#e6edf3] block mb-0.5">
                Historical Model Validation Notice
              </span>
              Engine performance validated against historical satellite detections and meteorological reanalysis.
              This validation does not constitute operational safety certification, guaranteed boundary accuracy,
              or regulatory approval.
            </div>

            {isValidatingLoading && (
              <div className="flex items-center gap-2 text-xs text-[#8b98a9] py-2">
                <span className="w-1.5 h-1.5 rounded-full bg-[#ff6a2b] animate-pulse" aria-hidden="true" />
                Loading empirical validation dataset…
              </div>
            )}

            {validationError && (
              <div className="p-2 text-xs text-[#ff3b30] bg-[#ff3b30]/10 border border-[#ff3b30]/20 rounded">
                {validationError}
              </div>
            )}

            {!isValidatingLoading && !validationError && (!validationData || !validationData.available) && (
              <div className="text-xs text-[#8b98a9] py-2">
                Empirical validation report is currently unavailable from the backend.
              </div>
            )}

            {!isValidatingLoading && validationData?.available && (
              <div className="flex flex-col gap-3">
                {/* Summary Metrics Cards */}
                {validationData.summary && Object.keys(validationData.summary).length > 0 && (
                  <div className="grid grid-cols-3 gap-1.5">
                    {validationData.summary.held_out_test_recall !== undefined && (
                      <div className="p-2 bg-[#0d141d] rounded border border-[#162733]">
                        <span className="text-[9px] uppercase tracking-wider text-[#657787] block">Test Recall</span>
                        <span className="text-xs font-mono font-bold text-[#2ecc71]">
                          {(Number(validationData.summary.held_out_test_recall) * 100).toFixed(1)}%
                        </span>
                      </div>
                    )}
                    {validationData.summary.baseline_recall !== undefined && (
                      <div className="p-2 bg-[#0d141d] rounded border border-[#162733]">
                        <span className="text-[9px] uppercase tracking-wider text-[#657787] block">Baseline Recall</span>
                        <span className="text-xs font-mono font-bold text-[#8b98a9]">
                          {(Number(validationData.summary.baseline_recall) * 100).toFixed(1)}%
                        </span>
                      </div>
                    )}
                    {validationData.summary.performance_margin !== undefined && (
                      <div className="p-2 bg-[#0d141d] rounded border border-[#162733]">
                        <span className="text-[9px] uppercase tracking-wider text-[#657787] block">Margin</span>
                        <span className="text-xs font-mono font-bold text-[#ff6a2b]">
                          {String(validationData.summary.performance_margin)}
                        </span>
                      </div>
                    )}
                  </div>
                )}

                {/* Calibrated Model Parameters */}
                {validationData.parameters && Object.keys(validationData.parameters).length > 0 && (
                  <div className="p-2 bg-[#090d12] rounded border border-[#162733]">
                    <span className="text-[9px] uppercase font-bold tracking-wider text-[#8b98a9] block mb-1">
                      Calibrated Grid-Search Parameters
                    </span>
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-[10px] font-mono">
                      {Object.entries(validationData.parameters).map(([k, v]) => (
                        <div key={k} className="flex items-center justify-between text-[#8b98a9]">
                          <span>{k}:</span>
                          <span className="text-[#e6edf3] font-semibold">{String(v)}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Performance Comparison Events Table */}
                {validationData.events && validationData.events.length > 0 && (
                  <div className="flex flex-col gap-1">
                    <span className="text-[10px] uppercase font-bold tracking-wider text-[#8b98a9]">
                      Historical Events Benchmarks ({validationData.events.length})
                    </span>
                    <div className="overflow-x-auto border border-[#162733] rounded">
                      <table className="w-full text-left border-collapse text-[10px]">
                        <thead>
                          <tr className="border-b border-[#162733] bg-[#0d141d] text-[#657787]">
                            <th className="p-1.5 font-semibold">Event</th>
                            <th className="p-1.5 font-semibold">Split</th>
                            <th className="p-1.5 font-semibold">Grid</th>
                            <th className="p-1.5 font-semibold text-right">Detections</th>
                            <th className="p-1.5 font-semibold text-right">Model</th>
                            <th className="p-1.5 font-semibold text-right">Baseline</th>
                            <th className="p-1.5 font-semibold text-right">Area (ha)</th>
                            <th className="p-1.5 font-semibold text-right">Bearing Err</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-[#162733]">
                          {validationData.events.map((ev, i) => {
                            const isTest = ev.split === 'test';
                            const modelRecallPct =
                              typeof ev.model_recall === 'number'
                                ? `${(ev.model_recall * 100).toFixed(1)}%`
                                : String(ev.model_recall);
                            const baselineRecallPct =
                              typeof ev.baseline_recall === 'number'
                                ? `${(ev.baseline_recall * 100).toFixed(1)}%`
                                : String(ev.baseline_recall);

                            return (
                              <tr key={i} className="hover:bg-[#0d141d]/50 transition-colors">
                                <td className="p-1.5 font-medium text-[#e6edf3] truncate max-w-[120px]" title={ev.event}>
                                  {ev.event}
                                </td>
                                <td className="p-1.5">
                                  <span
                                    className={`px-1 py-0.5 rounded text-[9px] font-bold uppercase ${
                                      isTest
                                        ? 'bg-[#2ecc71]/15 text-[#2ecc71] border border-[#2ecc71]/30'
                                        : 'bg-[#657787]/15 text-[#8b98a9]'
                                    }`}
                                  >
                                    {ev.split}
                                  </span>
                                </td>
                                <td className="p-1.5 text-[#8b98a9] font-mono whitespace-nowrap">{ev.grid}</td>
                                <td className="p-1.5 text-right font-mono text-[#e6edf3]">{ev.future_detections}</td>
                                <td className="p-1.5 text-right font-mono font-semibold text-[#2ecc71]">{modelRecallPct}</td>
                                <td className="p-1.5 text-right font-mono text-[#8b98a9]">{baselineRecallPct}</td>
                                <td className="p-1.5 text-right font-mono text-[#e6edf3]">{ev.predicted_area_ha}</td>
                                <td className="p-1.5 text-right font-mono text-[#e6edf3]">{ev.bearing_error_deg}°</td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* ─── TAB 2: Model Assumptions ──────────────────────────────────── */}
        {activeTab === 'assumptions' && (
          <div className="flex flex-col gap-2">
            {isAssumptionsLoading && (
              <div className="flex items-center gap-2 text-xs text-[#8b98a9] py-2">
                <span className="w-1.5 h-1.5 rounded-full bg-[#ff6a2b] animate-pulse" aria-hidden="true" />
                Loading engineering assumptions document…
              </div>
            )}

            {assumptionsError && (
              <div className="p-2 text-xs text-[#ff3b30] bg-[#ff3b30]/10 border border-[#ff3b30]/20 rounded">
                {assumptionsError}
              </div>
            )}

            {!isAssumptionsLoading && !assumptionsError && !hasValidAssumptions && (
              <div className="p-3 bg-[#0d141d] rounded border border-[#162733] text-center">
                <span className="text-base text-[#657787] block mb-1">ⓘ</span>
                <span className="text-xs font-semibold text-[#e6edf3] block mb-1">
                  Assumptions Documentation Unavailable
                </span>
                <p className="text-[11px] text-[#8b98a9] leading-relaxed">
                  The backend engineering assumptions document (<code className="text-[#e6edf3]">docs/assumptions.md</code>) is currently empty.
                  Physical assumptions will appear here when published by the core modeling team.
                </p>
              </div>
            )}

            {!isAssumptionsLoading && hasValidAssumptions && assumptionsText && (
              <div className="text-xs text-[#8b98a9] leading-relaxed whitespace-pre-line bg-[#0d141d] p-3 rounded border border-[#162733] max-h-96 overflow-y-auto">
                {assumptionsText}
              </div>
            )}
          </div>
        )}
      </div>
    </Panel>
  );
}

