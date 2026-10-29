import * as T from 'three';

const ACCENT = 0x276653;
const EPS = 1e-8;
const finite = value => value != null && value !== '' && Number.isFinite(Number(value));
const vector = value => value && finite(value.x) && finite(value.y) && finite(value.z);
const clamp = (value, handle) => Math.min(finite(handle.max) ? Number(handle.max) : Infinity,
  Math.max(finite(handle.min) ? Number(handle.min) : -Infinity, value));

/** Direct gestures change only values provided by the host's original controls. */
export function createDirectManipulation({ scene, camera, canvas, orbit, host,
  getHandles, getPickObjects, onChange, onDirty = () => {}, onSelect = () => {},
  onDragStart = () => {}, onDragEnd = () => {} }) {
  let disposed = false;
  let handles = [];
  let selected = null;
  let signature = null;
  let drag = null;
  let holdingKey = null;
  let highlightRoots = [];
  let highlighting = [];
  let screenPath = [];
  let currentRadius = 1;
  let contact = null;
  let lastHoverTime = 0;
  const listeners = [];
  const chips = new Map();
  const markers = new Map();
  const raycaster = new T.Raycaster();
  const ndc = new T.Vector2();
  const projected = new T.Vector3();
  const owned = new T.Group();
  owned.name = 'direct-manipulation-guides';
  owned.userData.directManipulation = true;
  scene.add(owned);
  const axisGroup = new T.Group();
  owned.add(axisGroup);
  const highlightGroup = new T.Group();
  owned.add(highlightGroup);
  const contactGroup = new T.Group();
  contactGroup.visible = false;
  owned.add(contactGroup);
  const contactFill = new T.Mesh(new T.CircleGeometry(1, 40), new T.MeshBasicMaterial({
    color: 0x76b89a, transparent: true, opacity: .15, depthWrite: false, side: T.DoubleSide,
    polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2 }));
  const contactRing = new T.Mesh(new T.RingGeometry(.94, 1, 40), new T.MeshBasicMaterial({
    color: 0x43896b, transparent: true, opacity: .8, depthWrite: false, side: T.DoubleSide,
    polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2 }));
  contactFill.renderOrder = contactRing.renderOrder = 102;
  contactGroup.add(contactFill, contactRing);
  const lineMaterial = new T.LineBasicMaterial({ color: ACCENT, transparent: true, opacity: .88,
    depthTest: false, depthWrite: false });
  const ringPoints = Array.from({ length: 80 }, (_, i) =>
    new T.Vector3(Math.cos(i / 80 * Math.PI * 2), Math.sin(i / 80 * Math.PI * 2), 0));
  const ring = new T.LineLoop(new T.BufferGeometry().setFromPoints(ringPoints), lineMaterial);
  ring.renderOrder = 1001;
  axisGroup.add(ring);
  const axialLine = new T.Line(new T.BufferGeometry().setFromPoints([
    new T.Vector3(0, 0, -1.1), new T.Vector3(0, 0, 1.1)
  ]), lineMaterial);
  axialLine.renderOrder = 1001;
  axisGroup.add(axialLine);
  const arrows = [new T.ArrowHelper(new T.Vector3(0, 1, 0), new T.Vector3(1, -.26, 0), .52, ACCENT, .18, .12),
    new T.ArrowHelper(new T.Vector3(0, -1, 0), new T.Vector3(-1, .26, 0), .52, ACCENT, .18, .12),
    new T.ArrowHelper(new T.Vector3(0, 0, 1), new T.Vector3(), 1.1, ACCENT, .22, .15),
    new T.ArrowHelper(new T.Vector3(0, 0, -1), new T.Vector3(), 1.1, ACCENT, .22, .15)];
  for (const arrow of arrows) {
    arrow.traverse(object => {
      object.renderOrder = 1002;
      if (object.geometry) object.geometry = object.geometry.clone();
      if (object.material) { object.material.depthTest = false; object.material.depthWrite = false; }
    });
    axisGroup.add(arrow);
  }
  axisGroup.visible = false;
  const highlightMaterial = new T.MeshBasicMaterial({ color: ACCENT, transparent: true, opacity: .14,
    depthWrite: false, depthTest: true, side: T.DoubleSide, polygonOffset: true,
    polygonOffsetFactor: -2, polygonOffsetUnits: -2 });

  const element = (tag, className, parent, text) => {
    const node = document.createElement(tag);
    node.className = className;
    if (text) node.textContent = text;
    parent?.append(node);
    return node;
  };
  const panel = element('section', 'dm-panel', host);
  panel.setAttribute('aria-label', 'Direct object controls');
  const hint = element('p', 'dm-hint', panel, 'Select a part to move · Drag blank space to orbit');
  const chipRow = element('div', 'dm-chips', panel);
  chipRow.setAttribute('aria-label', 'Movable parts');
  const readout = element('div', 'dm-readout', panel);
  readout.hidden = true;
  const titleRow = element('div', 'dm-title-row', readout);
  const title = element('strong', 'dm-title', titleRow);
  const valueText = element('output', 'dm-value', titleRow);
  const detailText = element('p', 'dm-detail', readout);
  const contactLabel = element('span', 'dm-contact-label', host);
  contactLabel.hidden = true;
  contactLabel.setAttribute('aria-hidden', 'true');
  const markerLayer = element('div', 'dm-markers', host);
  markerLayer.setAttribute('aria-hidden', 'true');
  host.classList.add('direct-manipulation-enabled');
  if (!canvas.hasAttribute('tabindex')) canvas.tabIndex = 0;
  const on = (target, type, callback, options) => {
    target.addEventListener(type, callback, options);
    listeners.push(() => target.removeEventListener(type, callback, options));
  };
  const usableAxis = h => !!(vector(h?.origin) && vector(h?.axis) && h.axis.lengthSq() > EPS);
  const isSoft = h => h?.interaction === 'soft';
  const softHintFor = h => h?.action === 'pull' ? 'Drag to pull · Release to settle' : 'Press and drag · Release to spring back';
  const axisKind = h => isSoft(h) ? null : h.kind === 'hinge' ? 'hinge' : h.kind === 'replay' ? h.axisKind : 'slide';
  const genericMotion = h => h?.kind === 'replay' && !isSoft(h) && !usableAxis(h);
  const labelFor = h => h.kind === 'replay' && /recorded|timeline|clip|motion|animation/i.test(h.label || '') ? 'Move object' : h.label || 'Part';
  const current = () => handles.find(h => h.id === selected) || null;
  const range = h => finite(h.min) && finite(h.max) && h.max > h.min ? h.max - h.min : Math.PI * 2;
  const formatted = (value, h) => {
    if (!finite(value)) return '—';
    value = Number(value);
    if (h.unit === 'rad') return `${(value * 180 / Math.PI).toFixed(1)}°`;
    if (h.unit === 'm') return `${(value * 1000).toFixed(1)} mm`;
    if (h.unit === '%' || h.kind === 'surface') return `${(value * (Math.abs(h.max) <= 1 ? 100 : 1)).toFixed(0)}%`;
    return `${value.toFixed(2)}${h.unit ? ` ${h.unit}` : ''}`;
  };
  function toScreen(position) {
    const rect = canvas.getBoundingClientRect();
    projected.copy(position).project(camera);
    return { x: rect.left + (projected.x + 1) * rect.width / 2,
      y: rect.top + (1 - projected.y) * rect.height / 2,
      visible: projected.z >= -1 && projected.z <= 1 };
  }
  function worldPerPixel(position) {
    const height = Math.max(1, canvas.clientHeight);
    if (camera.isOrthographicCamera) return (camera.top - camera.bottom) / camera.zoom / height;
    const local = position.clone().applyMatrix4(camera.matrixWorldInverse);
    return Math.max(.000001, -local.z * 2 * Math.tan(T.MathUtils.degToRad(camera.fov / 2)) / height);
  }
  function setRay(x, y) {
    const rect = canvas.getBoundingClientRect();
    ndc.set((x - rect.left) / rect.width * 2 - 1, -(y - rect.top) / rect.height * 2 + 1);
    raycaster.setFromCamera(ndc, camera);
    return raycaster.ray;
  }
  function clearHighlight() {
    for (const pair of highlighting) highlightGroup.remove(pair.overlay);
    highlighting = [];
    highlightRoots = [];
  }
  function highlight(handle) {
    const roots = isSoft(handle) || genericMotion(handle) ? [] : handle?.objects || [];
    if (roots.length === highlightRoots.length && roots.every((root, i) => root === highlightRoots[i])) return;
    clearHighlight();
    highlightRoots = roots.slice();
    const seen = new Set();
    for (const root of roots) root?.traverse(source => {
      if (!source.isMesh || seen.has(source) || !source.geometry) return;
      seen.add(source);
      const overlay = source.isSkinnedMesh ? new T.SkinnedMesh(source.geometry, highlightMaterial) :
        new T.Mesh(source.geometry, highlightMaterial);
      if (source.isSkinnedMesh) {
        overlay.skeleton = source.skeleton;
        overlay.bindMode = source.bindMode;
        overlay.bindMatrix.copy(source.bindMatrix);
        overlay.bindMatrixInverse.copy(source.bindMatrixInverse);
      }
      overlay.matrixAutoUpdate = false;
      overlay.frustumCulled = false;
      overlay.renderOrder = 100;
      highlightGroup.add(overlay);
      highlighting.push({ source, overlay });
    });
  }
  function updateHighlight() {
    for (const { source, overlay } of highlighting) {
      overlay.matrix.copy(source.matrixWorld);
      overlay.matrixWorldNeedsUpdate = true;
      let visible = true;
      for (let node = source; node; node = node.parent) if (!node.visible) { visible = false; break; }
      overlay.visible = visible;
      if (source.morphTargetInfluences) overlay.morphTargetInfluences = source.morphTargetInfluences;
    }
  }
  function surfaceNormal(hit) {
    const normal = (hit.normal || hit.face?.normal || new T.Vector3(0, 0, 1)).clone();
    if (hit.face && hit.object.getVertexPosition) {
      const a = hit.object.getVertexPosition(hit.face.a, new T.Vector3());
      const b = hit.object.getVertexPosition(hit.face.b, new T.Vector3());
      const c = hit.object.getVertexPosition(hit.face.c, new T.Vector3());
      const faceNormal = new T.Vector3().crossVectors(b.sub(a), c.sub(a));
      if (faceNormal.lengthSq() > EPS) normal.copy(faceNormal);
    }
    normal.applyNormalMatrix(new T.Matrix3().getNormalMatrix(hit.object.matrixWorld)).normalize();
    if (normal.dot(raycaster.ray.direction) > 0) normal.negate();
    return normal;
  }
  function setContact(handle, hit) {
    if (!handle || !hit) {
      if (contact) onDirty();
      contact = null; contactGroup.visible = false; contactLabel.hidden = true;
      host.classList.remove('dm-soft-hover');
      return;
    }
    contact = { id: handle.id, point: hit.point.clone(), normal: surfaceNormal(hit), object: hit.object,
      localPoint: hit.object.worldToLocal(hit.point.clone()), face: hit.face, barycentric: null };
    if (hit.face && hit.object.getVertexPosition) {
      const a = hit.object.getVertexPosition(hit.face.a, new T.Vector3());
      const b = hit.object.getVertexPosition(hit.face.b, new T.Vector3());
      const c = hit.object.getVertexPosition(hit.face.c, new T.Vector3());
      contact.barycentric = T.Triangle.getBarycoord(contact.localPoint, a, b, c, new T.Vector3());
    }
    host.classList.add('dm-soft-hover');
    updateContact(); onDirty();
  }
  function updateContact() {
    if (!contact) return;
    const h = handles.find(handle => handle.id === contact.id);
    let belongs = false;
    for (const root of h?.objects || []) {
      for (let node = contact.object; node; node = node.parent) if (node === root) { belongs = true; break; }
    }
    if (!h || !isSoft(h) || !belongs) { setContact(null); return; }
    if (contact.barycentric && contact.face) {
      const a = contact.object.getVertexPosition(contact.face.a, new T.Vector3());
      const b = contact.object.getVertexPosition(contact.face.b, new T.Vector3());
      const c = contact.object.getVertexPosition(contact.face.c, new T.Vector3());
      contact.localPoint.copy(a).multiplyScalar(contact.barycentric.x)
        .addScaledVector(b, contact.barycentric.y).addScaledVector(c, contact.barycentric.z);
      const normal = new T.Vector3().crossVectors(b.clone().sub(a), c.clone().sub(a))
        .applyNormalMatrix(new T.Matrix3().getNormalMatrix(contact.object.matrixWorld)).normalize();
      if (normal.lengthSq() > EPS) {
        if (normal.dot(contact.normal) < 0) normal.negate();
        contact.normal.copy(normal);
      }
    }
    contact.point.copy(contact.localPoint).applyMatrix4(contact.object.matrixWorld);
    const p = toScreen(contact.point);
    contactGroup.visible = p.visible;
    contactLabel.hidden = !p.visible;
    if (!p.visible) return;
    const wpp = worldPerPixel(contact.point);
    contactGroup.position.copy(contact.point).addScaledVector(contact.normal, wpp * .7);
    contactGroup.quaternion.setFromUnitVectors(new T.Vector3(0, 0, 1), contact.normal);
    contactGroup.scale.setScalar(wpp * (drag?.id === h.id ? 17 : 19));
    contactFill.material.opacity = drag?.id === h.id ? .23 : .13;
    const rect = host.getBoundingClientRect();
    contactLabel.textContent = h.action === 'pull' ? 'Pull' : 'Press';
    contactLabel.style.left = `${Math.min(rect.width - 64, Math.max(6, p.x - rect.left + 24))}px`;
    contactLabel.style.top = `${Math.min(rect.height - 26, Math.max(6, p.y - rect.top - 12))}px`;
  }
  function select(id) {
    if (disposed) return;
    const h = handles.find(item => item.id === id) || null;
    if (drag && drag.id !== h?.id) finish(true, 'selection');
    selected = h?.id || null;
    highlight(h);
    for (const [chipId, chip] of chips) chip.setAttribute('aria-pressed', String(chipId === selected));
    onSelect(h);
    updateReadout();
    updateGuides();
    onDirty();
  }
  function rebuild() {
    chipRow.replaceChildren();
    chips.clear();
    markerLayer.replaceChildren();
    markers.clear();
    for (const h of handles) {
      const chip = element('button', 'dm-chip', chipRow);
      const symbol = isSoft(h) ? '≈' : h.kind === 'hinge' ? '↻' : h.kind === 'slide' ? '↔' : h.kind === 'surface' ? '≈' : '↔';
      element('span', 'dm-chip-symbol', chip, symbol).setAttribute('aria-hidden', 'true');
      element('span', 'dm-chip-label', chip, labelFor(h));
      chip.type = 'button';
      chip.dataset.directId = h.id;
      chip.setAttribute('aria-pressed', String(h.id === selected));
      chip.title = isSoft(h) ? softHintFor(h) : h.kind === 'replay' ? 'Drag to move' : h.description || h.axisLabel || h.label || '';
      chip.addEventListener('click', () => { select(h.id); chip.focus({ preventScroll: true }); });
      chips.set(h.id, chip);
      const marker = element('span', 'dm-marker', markerLayer);
      marker.dataset.directId = h.id;
      markers.set(h.id, marker);
    }
    chipRow.hidden = handles.length === 0 || (handles.length === 1 && genericMotion(handles[0]));
    panel.classList.toggle('dm-static', handles.length === 0);
    hint.textContent = handles.length ? 'Select a part to move · Drag blank space to orbit' : 'Drag to orbit · Scroll to zoom';
  }
  function sync() {
    handles = (getHandles?.() || []).filter(h => h && h.id != null);
    const nextSignature = handles.map(h => `${h.id}|${h.label}|${h.kind}|${h.interaction}|${h.disabled}`).join('\n');
    if (nextSignature !== signature) { signature = nextSignature; rebuild(); }
    if (selected && !current()) {
      if (drag) finish(true, 'unavailable');
      selected = null;
      clearHighlight();
      onSelect(null);
    }
    if (!selected && handles.length === 1 && genericMotion(handles[0])) selected = handles[0].id;
    const h = current();
    if (drag && h?.disabled) finish(true, 'disabled');
    highlight(h);
  }
  function updateReadout() {
    const h = current();
    readout.hidden = !h || isSoft(h) || h.kind === 'replay';
    panel.classList.toggle('dm-selected', !!h);
    const softHint = isSoft(h) || (!h && handles.length && handles.every(isSoft));
    panel.classList.toggle('dm-soft', !!softHint);
    const softHintHandle = h || (handles.every(handle => handle.action === 'pull') ? { action: 'pull' } : null);
    hint.textContent = softHint ? softHintFor(softHintHandle) :
      !handles.length ? 'Drag to orbit · Scroll to zoom' : !h ? 'Select a part to move · Drag blank space to orbit' :
      h.kind === 'hinge' ? 'Drag the part or ring · Drag blank space to orbit' :
      h.kind === 'replay' ? 'Drag to move · Drag blank space to orbit' :
      'Drag the part or arrow · Drag blank space to orbit';
    if (!h || isSoft(h) || h.kind === 'replay') return;
    title.textContent = h.label || 'Selected part';
    valueText.textContent = formatted(h.value, h);
    const bounds = finite(h.min) && finite(h.max) ? `${formatted(h.min, h)} – ${formatted(h.max, h)}` : 'Continuous';
    const prefix = h.axisLabel || (h.kind === 'hinge' ? 'Rotation' : h.kind === 'surface' ? 'Surface movement' : 'Translation');
    detailText.textContent = `${prefix} · ${bounds}${h.disabled ? ' · Unavailable' : ''}`;
    detailText.title = h.description || '';
  }
  function updateGuides() {
    const h = current();
    axisGroup.visible = !!h && usableAxis(h) && !!axisKind(h);
    screenPath = [];
    if (axisGroup.visible) {
      currentRadius = worldPerPixel(h.origin) * (canvas.clientWidth < 500 ? 48 : 60);
      axisGroup.position.copy(h.origin);
      axisGroup.quaternion.setFromUnitVectors(new T.Vector3(0, 0, 1), h.axis.clone().normalize());
      axisGroup.scale.setScalar(currentRadius);
      const rotation = axisKind(h) === 'hinge';
      ring.visible = rotation;
      axialLine.visible = !rotation;
      arrows[0].visible = arrows[1].visible = rotation;
      arrows[2].visible = arrows[3].visible = !rotation;
      axisGroup.updateMatrixWorld(true);
      if (rotation) {
        for (let i = 0; i <= 80; i++) {
          const p = new T.Vector3(Math.cos(i / 80 * Math.PI * 2), Math.sin(i / 80 * Math.PI * 2), 0);
          screenPath.push(toScreen(p.applyMatrix4(axisGroup.matrixWorld)));
        }
      } else {
        screenPath = [-1.1, 1.1].map(z => toScreen(new T.Vector3(0, 0, z).applyMatrix4(axisGroup.matrixWorld)));
      }
    }
    const hostRect = host.getBoundingClientRect();
    for (const handle of handles) {
      const marker = markers.get(handle.id);
      if (!marker) continue;
      const p = !isSoft(handle) && usableAxis(handle) ? toScreen(handle.origin) : null;
      marker.hidden = !p?.visible;
      if (p?.visible) {
        marker.style.transform = `translate(${p.x - hostRect.left}px,${p.y - hostRect.top}px)`;
        marker.classList.toggle('dm-marker-selected', handle.id === selected);
      }
    }
  }
  function update() {
    if (disposed) return;
    sync();
    updateReadout();
    updateGuides();
    updateHighlight();
    updateContact();
  }
  function refresh() { signature = null; update(); }
  const segmentDistance = (x, y, a, b) => {
    const dx = b.x - a.x, dy = b.y - a.y;
    const t = Math.max(0, Math.min(1, ((x - a.x) * dx + (y - a.y) * dy) / (dx * dx + dy * dy || 1)));
    return Math.hypot(x - a.x - dx * t, y - a.y - dy * t);
  };
  function pick(event) {
    const tolerance = event.pointerType === 'touch' ? 22 : 10;
    const active = current();
    if (active && !active.disabled) {
      for (let i = 1; i < screenPath.length; i++) {
        if (screenPath[i - 1].visible && screenPath[i].visible &&
            segmentDistance(event.clientX, event.clientY, screenPath[i - 1], screenPath[i]) < tolerance) return { handle: active, hit: null };
      }
    }
    const candidates = handles.filter(h => !h.disabled);
    let pivotHit = null, pivotDistance = tolerance;
    for (const h of candidates) {
      if (isSoft(h) || !usableAxis(h)) continue;
      const p = toScreen(h.origin);
      const distance = Math.hypot(event.clientX - p.x, event.clientY - p.y);
      if (p.visible && distance < pivotDistance) { pivotHit = h; pivotDistance = distance; }
    }
    setRay(event.clientX, event.clientY);
    // Include stationary geometry so a moving part cannot be picked through its casing.
    const roots = getPickObjects ? getPickObjects() : scene.children.filter(object =>
      object !== owned && !object.userData.directManipulation && !/ground|floor/i.test(object.name));
    const hits = raycaster.intersectObjects(roots, true);
    for (const hit of hits) {
      if (!hit.object.isMesh) continue;
      let visible = true;
      for (let node = hit.object; node; node = node.parent) if (!node.visible) visible = false;
      if (!visible) continue;
      const matches = [];
      for (const h of candidates) {
        let distance = Infinity;
        for (const root of h.objects || []) {
          let depth = 0;
          for (let node = hit.object; node; node = node.parent, depth++) {
            if (node === root) { distance = Math.min(distance, depth); break; }
          }
        }
        if (Number.isFinite(distance) && (!h.acceptsHit || h.acceptsHit(hit))) matches.push({ h, distance });
      }
      matches.sort((a, b) => Number(isSoft(b.h)) - Number(isSoft(a.h)) || a.distance - b.distance ||
        (Number(b.h.selectionDepth) || 0) - (Number(a.h.selectionDepth) || 0) ||
        (a.h.objects?.length || 0) - (b.h.objects?.length || 0) ||
        Number(b.h.id === selected) - Number(a.h.id === selected));
      if (matches.length) return pivotHit && pivotDistance < 5 ? { handle: pivotHit, hit: null } : { handle: matches[0].h, hit };
      return pivotHit ? { handle: pivotHit, hit: null } : null;
    }
    return pivotHit ? { handle: pivotHit, hit: null } : null;
  }
  function planeVector(state, x, y) {
    const ray = setRay(x, y);
    // Preserve the exact 3D solution for narrow ellipses; only a nearly parallel
    // ray needs the projected-arc fallback (a side-on ring has two screen branches).
    if (Math.abs(ray.direction.dot(state.axis)) < .002) return null;
    const point = ray.intersectPlane(new T.Plane().setFromNormalAndCoplanarPoint(state.axis, state.origin), new T.Vector3());
    if (!point) return null;
    const v = point.sub(state.origin);
    return v.lengthSq() > EPS ? v.normalize() : null;
  }
  function ringProjection(state, angle) {
    const local = new T.Vector3(Math.cos(angle), Math.sin(angle), 0)
      .applyQuaternion(state.ringRotation).multiplyScalar(state.ringRadius).add(state.origin);
    return toScreen(local);
  }
  function projectedAngularDelta(state, dx, dy) {
    const angle = state.ringAngle + state.angle;
    const a = ringProjection(state, angle - .04), b = ringProjection(state, angle + .04);
    let tx = (b.x - a.x) / .08, ty = (b.y - a.y) / .08;
    let magnitude = tx * tx + ty * ty;
    // A side-on ring has no radial screen tangent. Use its actual projected arc.
    // At a collapsed endpoint, keep the last usable arc direction instead.
    if (magnitude < 25) {
      tx = state.lastArc.x; ty = state.lastArc.y;
      magnitude = tx * tx + ty * ty;
    } else state.lastArc = { x: tx, y: ty };
    return Math.max(-.5, Math.min(.5, (dx * tx + dy * ty) / Math.max(25, magnitude)));
  }
  function begin(handle, event, source = 'pointer', hit = null) {
    if (disposed || drag || handle?.disabled) return false;
    select(handle.id);
    const now = performance.now();
    const origin = vector(handle.origin) ? handle.origin.clone() : new T.Vector3();
    const axis = usableAxis(handle) ? handle.axis.clone().normalize() : null;
    drag = { id: handle.id, handle, source, pointerId: event?.pointerId,
      startValue: Number(handle.value) || 0, lastValue: Number(handle.value) || 0,
      x: event?.clientX || 0, y: event?.clientY || 0,
      startX: event?.clientX || 0, startY: event?.clientY || 0,
      time: now, lastTime: now, origin, axis, angle: 0,
      orbitEnabled: orbit?.enabled, orbitAutoRotate: orbit?.autoRotate,
      target: canvas, hit: hit ? { point: hit.point.clone(), normal: surfaceNormal(hit), object: hit.object,
        faceIndex: hit.faceIndex, face: hit.face, uv: hit.uv?.clone() || null } : null };
    drag.pressBase = clamp(Math.max(drag.startValue, finite(handle.pressAmount) ? Number(handle.pressAmount) :
      Number(handle.min || 0) + range(handle) * .18), handle);
    if (axis) {
      drag.wpp = worldPerPixel(origin);
      const a = toScreen(origin), b = toScreen(origin.clone().addScaledVector(axis, drag.wpp * 100));
      drag.screenAxis = { x: (b.x - a.x) / 100, y: (b.y - a.y) / 100 };
      if (handle.kind === 'hinge') {
        drag.lastPlane = planeVector(drag, drag.x, drag.y);
        drag.useProjectedArc = !drag.lastPlane;
        drag.ringRotation = new T.Quaternion().setFromUnitVectors(new T.Vector3(0, 0, 1), axis);
        drag.ringRadius = currentRadius;
        let best = Infinity;
        drag.ringAngle = 0;
        for (let i = 0; i < 360; i++) {
          const angle = i / 360 * Math.PI * 2;
          const p = ringProjection(drag, angle);
          const distance = (p.x - drag.x) ** 2 + (p.y - drag.y) ** 2;
          if (distance < best) { best = distance; drag.ringAngle = angle; }
        }
        const p = ringProjection(drag, drag.ringAngle - .15), q = ringProjection(drag, drag.ringAngle + .15);
        drag.lastArc = { x: (q.x - p.x) / .3, y: (q.y - p.y) / .3 };
        if (drag.lastArc.x ** 2 + drag.lastArc.y ** 2 < 25) {
          const x0 = ringProjection(drag, 0), x1 = ringProjection(drag, Math.PI);
          const y0 = ringProjection(drag, Math.PI / 2), y1 = ringProjection(drag, -Math.PI / 2);
          const x = { x: (x0.x - x1.x) / 2, y: (x0.y - x1.y) / 2 };
          const y = { x: (y0.x - y1.x) / 2, y: (y0.y - y1.y) / 2 };
          drag.lastArc = x.x ** 2 + x.y ** 2 > y.x ** 2 + y.y ** 2 ? x : y;
        }
      }
    }
    if (orbit) { orbit.enabled = false; orbit.autoRotate = false; }
    host.classList.add('dm-dragging');
    if (isSoft(handle)) setContact(handle, hit);
    onDragStart(handle, { source, startValue: drag.startValue, elapsed: 0, dt: 0,
      point: drag.hit?.point || null, normal: drag.hit?.normal || null, object: drag.hit?.object || null,
      faceIndex: drag.hit?.faceIndex ?? null, face: drag.hit?.face || null, uv: drag.hit?.uv || null });
    if (isSoft(handle) && source === 'pointer') change(drag.pressBase);
    if (event?.pointerId != null) {
      try { drag.target.setPointerCapture(event.pointerId); } catch (_) { /* A removed canvas has no pointer capture. */ }
    }
    return true;
  }
  function change(value, source = drag?.source) {
    if (!drag) return;
    const h = handles.find(item => item.id === drag.id) || drag.handle;
    value = clamp(value, h);
    if (!Number.isFinite(value)) return;
    const now = performance.now();
    const detail = { source, delta: value - drag.lastValue, startValue: drag.startValue,
      elapsed: (now - drag.time) / 1000, dt: Math.max(.008, (now - drag.lastTime) / 1000) };
    drag.lastValue = value;
    drag.lastTime = now;
    onChange?.(drag.id, value, detail);
    onDirty();
  }
  function finish(cancelled = false, reason = 'release') {
    if (!drag) return;
    const state = drag;
    // Revert the host's target before releasing a force/velocity actuator.
    if (cancelled && reason === 'escape') change(state.startValue, state.source);
    drag = null;
    holdingKey = null;
    if (orbit) { orbit.enabled = state.orbitEnabled; orbit.autoRotate = state.orbitAutoRotate; }
    host.classList.remove('dm-dragging');
    if (state.pointerId != null) {
      try { if (state.target.hasPointerCapture(state.pointerId)) state.target.releasePointerCapture(state.pointerId); } catch (_) { /* The host may already be removed. */ }
    }
    onDragEnd(handles.find(h => h.id === state.id) || state.handle,
      { source: state.source, cancelled, reason, startValue: state.startValue, lastValue: state.lastValue,
        point: state.hit?.point || null, normal: state.hit?.normal || null, object: state.hit?.object || null,
        elapsed: (performance.now() - state.time) / 1000 });
    onDirty();
  }
  function move(event) {
    if (!drag) {
      if (event.buttons || event.pointerType === 'touch' || performance.now() - lastHoverTime < 40 || !handles.some(isSoft)) return;
      lastHoverTime = performance.now();
      const picked = pick(event);
      if (picked && isSoft(picked.handle) && picked.hit) setContact(picked.handle, picked.hit);
      else setContact(null);
      return;
    }
    if (event.pointerId !== drag.pointerId) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    const state = drag;
    const h = handles.find(item => item.id === state.id) || state.handle;
    let value = state.lastValue;
    if (isSoft(h)) {
      const direction = h.action === 'pull' ? -1 : 1;
      value = state.pressBase + (event.clientY - state.startY) * direction / 160 * range(h);
    } else if (h.kind === 'replay') {
      value = state.startValue + (event.clientX - state.startX) / Math.min(280, Math.max(160, canvas.clientWidth * .5)) * range(h);
    } else if (h.kind === 'hinge' && state.axis) {
      const v = state.useProjectedArc ? null : planeVector(state, event.clientX, event.clientY);
      if (v && state.lastPlane) {
        state.angle += Math.atan2(state.axis.dot(new T.Vector3().crossVectors(state.lastPlane, v)), state.lastPlane.dot(v));
      } else {
        state.angle += projectedAngularDelta(state, event.clientX - state.x, event.clientY - state.y);
      }
      state.lastPlane = v;
      value = state.startValue + state.angle;
    } else {
      const screen = state.screenAxis || { x: 1, y: 0 };
      const lengthSq = screen.x * screen.x + screen.y * screen.y;
      const pixels = lengthSq > .025 ? ((event.clientX - state.startX) * screen.x +
        (event.clientY - state.startY) * screen.y) / lengthSq : event.clientX - state.startX;
      value = state.startValue + (h.kind === 'surface' ? pixels / 160 * range(h) : pixels * (state.wpp || range(h) / 200));
    }
    state.x = event.clientX;
    state.y = event.clientY;
    change(value);
  }
  function pointerDown(event) {
    if (disposed || event.button !== 0 || event.isPrimary === false) return;
    if (drag) { event.preventDefault(); event.stopImmediatePropagation(); return; }
    update();
    const picked = pick(event), h = picked?.handle;
    if (!h || h.disabled) { setContact(null); return; }
    event.preventDefault();
    event.stopImmediatePropagation();
    if (begin(h, event, 'pointer', picked.hit)) canvas.focus({ preventScroll: true });
  }
  function pointerEnd(event) {
    if (!drag || event.pointerId !== drag.pointerId) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    finish(event.type !== 'pointerup', event.type);
  }
  for (const target of [canvas]) {
    on(target, 'pointerdown', pointerDown, { capture: true, passive: false });
    on(target, 'pointermove', move, { capture: true, passive: false });
    on(target, 'pointerup', pointerEnd, { capture: true, passive: false });
    on(target, 'pointercancel', pointerEnd, { capture: true, passive: false });
    on(target, 'lostpointercapture', event => {
      if (drag && drag.pointerId === event.pointerId) finish(true, 'lostcapture');
    });
  }
  on(canvas, 'pointerleave', () => { if (!drag) setContact(null); });
  on(document, 'keydown', event => {
    if (disposed) return;
    if (event.key === 'Escape') {
      if (drag) { event.preventDefault(); event.stopImmediatePropagation(); finish(true, 'escape'); }
      return;
    }
    if (event.altKey || event.ctrlKey || event.metaKey) return;
    if (event.target !== canvas && !panel.contains(event.target)) return;
    const chipId = event.target.closest?.('[data-direct-id]')?.dataset.directId;
    if (chipId && chipId !== selected) select(chipId);
    const h = current();
    if (!h || h.disabled) return;
    const direction = { ArrowLeft: -1, ArrowDown: -1, ArrowRight: 1, ArrowUp: 1 }[event.key];
    if (direction) {
      event.preventDefault();
      event.stopImmediatePropagation();
      if (drag) return;
      const step = range(h) / (isSoft(h) ? 12.5 : 100) * (event.shiftKey ? 10 : 1);
      if (begin(h, null, 'keyboard')) { change(Number(h.value || 0) + direction * step, 'keyboard'); finish(false, 'keyboard'); }
    } else if (event.key === ' ' || event.key === 'Enter') {
      event.preventDefault();
      event.stopImmediatePropagation();
      if (!event.repeat && !drag && begin(h, null, 'keyboard')) {
        holdingKey = event.key;
        if (isSoft(h)) change(drag.pressBase, 'keyboard');
      }
    }
  }, true);
  on(document, 'keyup', event => {
    if (holdingKey && event.key === holdingKey) {
      event.preventDefault(); event.stopImmediatePropagation(); finish(false, 'keyup');
    }
  }, true);
  on(window, 'blur', () => { finish(true, 'blur'); setContact(null); });
  on(document, 'visibilitychange', () => { if (document.hidden) finish(true, 'hidden'); });

  function dispose() {
    if (disposed) return;
    finish(true, 'dispose');
    disposed = true;
    for (const remove of listeners) remove();
    clearHighlight();
    scene.remove(owned);
    const geometries = new Set(), materials = new Set();
    const collectOwned = object => {
      if (object.geometry) geometries.add(object.geometry);
      if (object.material) for (const material of [].concat(object.material)) materials.add(material);
    };
    axisGroup.traverse(collectOwned);
    contactGroup.traverse(collectOwned);
    for (const geometry of geometries) geometry.dispose();
    for (const material of materials) material.dispose();
    highlightMaterial.dispose();
    panel.remove();
    markerLayer.remove();
    contactLabel.remove();
    contact = null;
    handles = [];
    selected = null;
    screenPath = [];
    chips.clear();
    markers.clear();
    host.classList.remove('direct-manipulation-enabled', 'dm-dragging', 'dm-soft-hover');
  }
  refresh();
  return { update, refresh, dispose, select, get selectedId() { return selected; } };
}
