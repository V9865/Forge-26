/**
 * EmberRoute — Map popup DOM builders
 *
 * Builds popup content safely using DOM elements and textContent
 * to eliminate all HTML/XSS injection vectors from untrusted backend properties.
 */

import { formatArrivalMinutes } from '@/utils/format';

/**
 * Safely build settlement popup DOM element without HTML injection.
 */
export function createSettlementPopupNode(
  props: Record<string, unknown> | null | undefined,
): HTMLElement {
  const container = document.createElement('div');
  container.style.cssText =
    'font-family: inherit; font-size: 12px; color: #e6edf3; background: #121821; padding: 8px 10px; border-radius: 6px; border: 1.5px solid #162733; min-width: 150px; box-shadow: 0 4px 16px rgba(0,0,0,0.6);';

  // Title
  const title = document.createElement('div');
  title.style.cssText = 'font-weight: 700; font-size: 13px; margin-bottom: 4px; color: #ffffff;';
  title.textContent = typeof props?.name === 'string' && props.name ? props.name : 'Settlement';
  container.appendChild(title);

  // Status
  const statusRow = document.createElement('div');
  statusRow.style.cssText = 'color: #8b98a9; font-size: 11px; margin-bottom: 3px;';
  statusRow.textContent = 'Status: ';
  const statusSpan = document.createElement('span');
  const statusVal = typeof props?.status === 'string' ? props.status : 'UNKNOWN';
  let statusColor = '#657787';
  if (statusVal === 'EVACUATE') statusColor = '#2ecc71';
  else if (statusVal === 'TRAPPED') statusColor = '#ff3b30';
  else if (statusVal === 'ALREADY_BURNING') statusColor = '#8b1a1a';
  statusSpan.style.cssText = `font-weight: 700; color: ${statusColor};`;
  statusSpan.textContent = statusVal;
  statusRow.appendChild(statusSpan);
  container.appendChild(statusRow);

  // Fire arrival
  const arrivalMin = typeof props?.fire_arrival_min === 'number' ? props.fire_arrival_min : null;
  if (arrivalMin !== null) {
    const arrRow = document.createElement('div');
    arrRow.style.cssText = 'color: #8b98a9; font-size: 11px;';
    arrRow.textContent = 'Fire arrival: ';
    const arrSpan = document.createElement('span');
    arrSpan.style.cssText = 'font-family: monospace; color: #ff6a2b; font-weight: 600;';
    arrSpan.textContent = `+${formatArrivalMinutes(arrivalMin)}`;
    arrRow.appendChild(arrSpan);
    container.appendChild(arrRow);
  }

  // Depart by
  if (typeof props?.depart_by_min === 'number') {
    const depRow = document.createElement('div');
    depRow.style.cssText = 'color: #8b98a9; font-size: 11px;';
    depRow.textContent = 'Depart by: ';
    const depSpan = document.createElement('span');
    depSpan.style.cssText = 'font-family: monospace; color: #f5a524;';
    depSpan.textContent = `${props.depart_by_min} min`;
    depRow.appendChild(depSpan);
    container.appendChild(depRow);
  }

  // Travel time
  if (typeof props?.route_travel_min === 'number') {
    const travelRow = document.createElement('div');
    travelRow.style.cssText = 'color: #8b98a9; font-size: 11px;';
    travelRow.textContent = 'Travel time: ';
    const travelSpan = document.createElement('span');
    travelSpan.style.cssText = 'font-family: monospace; color: #00e676;';
    travelSpan.textContent = `${props.route_travel_min} min`;
    travelRow.appendChild(travelSpan);
    container.appendChild(travelRow);
  }

  // Note
  if (typeof props?.note === 'string' && props.note) {
    const noteEl = document.createElement('div');
    noteEl.style.cssText = 'color: #8b98a9; font-size: 10px; margin-top: 4px; font-style: italic; border-top: 1px solid #162733; padding-top: 3px;';
    noteEl.textContent = props.note;
    container.appendChild(noteEl);
  }

  return container;
}

/**
 * Safely build fire detection popup DOM element without HTML injection.
 */
export function createDetectionPopupNode(
  coords: [number, number],
  props: Record<string, unknown> | null | undefined,
): HTMLElement {
  const container = document.createElement('div');
  container.style.cssText =
    'font-family: inherit; font-size: 11px; color: #e6edf3; background: #121821; padding: 8px 10px; border-radius: 6px; border: 1.5px solid #ff6a2b/60; min-width: 145px; box-shadow: 0 4px 16px rgba(0,0,0,0.6);';

  // Title
  const title = document.createElement('div');
  title.style.cssText = 'font-weight: 700; color: #ff6a2b; margin-bottom: 3px; font-size: 12px; display: flex; align-items: center; gap: 4px;';
  title.textContent = '🔥 NASA FIRMS Detection';
  container.appendChild(title);

  // Coords
  const coordsRow = document.createElement('div');
  coordsRow.style.cssText = 'color: #8b98a9; margin-top: 2px;';
  coordsRow.textContent = 'Coords: ';
  const coordsSpan = document.createElement('span');
  coordsSpan.style.cssText = 'font-family: monospace; color: #e6edf3;';
  coordsSpan.textContent = `${coords[1].toFixed(4)}°N, ${coords[0].toFixed(4)}°E`;
  coordsRow.appendChild(coordsSpan);
  container.appendChild(coordsRow);

  // FRP
  if (props?.frp !== undefined && props.frp !== null) {
    const frpRow = document.createElement('div');
    frpRow.style.cssText = 'color: #8b98a9; margin-top: 1px;';
    frpRow.textContent = 'FRP: ';
    const frpSpan = document.createElement('span');
    frpSpan.style.cssText = 'font-family: monospace; color: #ff4500; font-weight: 600;';
    frpSpan.textContent = `${props.frp} MW`;
    frpRow.appendChild(frpSpan);
    container.appendChild(frpRow);
  }

  // Confidence
  if (props?.confidence !== undefined && props.confidence !== null) {
    const confRow = document.createElement('div');
    confRow.style.cssText = 'color: #8b98a9; margin-top: 1px;';
    confRow.textContent = 'Confidence: ';
    const confSpan = document.createElement('span');
    confSpan.style.cssText = 'color: #e6edf3;';
    confSpan.textContent = String(props.confidence);
    confRow.appendChild(confSpan);
    container.appendChild(confRow);
  }

  // Satellite
  if (typeof props?.satellite === 'string' && props.satellite) {
    const satRow = document.createElement('div');
    satRow.style.cssText = 'color: #8b98a9; margin-top: 1px;';
    satRow.textContent = 'Satellite: ';
    const satSpan = document.createElement('span');
    satSpan.style.cssText = 'color: #e6edf3;';
    satSpan.textContent = props.satellite;
    satRow.appendChild(satSpan);
    container.appendChild(satRow);
  }

  // Acquisition time
  if (typeof props?.acq_time_utc === 'string' && props.acq_time_utc) {
    const acqRow = document.createElement('div');
    acqRow.style.cssText = 'color: #8b98a9; margin-top: 1px; font-size: 10px;';
    acqRow.textContent = 'Acquired: ';
    const acqSpan = document.createElement('span');
    acqSpan.style.cssText = 'font-family: monospace; color: #8b98a9;';
    try {
      acqSpan.textContent = new Date(props.acq_time_utc).toISOString().slice(11, 19) + ' UTC';
    } catch {
      acqSpan.textContent = props.acq_time_utc;
    }
    acqRow.appendChild(acqSpan);
    container.appendChild(acqRow);
  }

  return container;
}
