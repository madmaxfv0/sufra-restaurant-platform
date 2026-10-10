/**
 * What a table IS, in words. The server computes `attributes` for every table
 * (booking.table_attributes); this turns them into the chips, meters and
 * sentences the panel, the hover card and the guide cards show. If the server
 * is older and sends no attributes, the same facts are derived here from the
 * scores, so the panel never goes blank.
 */
export function attributesOf(t, zone) {
  if (t.attributes) return t.attributes;
  const sc = t.scores || {}, tags = t.tags || [], d = t.distances || {};
  const outdoor = !!(zone && zone.outdoor);
  const u = 0.05;
  const noise = sc.noise == null ? 0.4 : sc.noise;
  const near_water = (sc.sea_view || 0) >= 0.6;
  const covered = tags.indexOf('umbrella') >= 0 || !outdoor;
  const best = [];
  if (sc.romantic > 0.7) best.push('a date');
  if (t.max_party >= 6) best.push('a group');
  if (sc.quiet > 0.75) best.push('quiet conversation');
  if (sc.business > 0.62) best.push('a working dinner');
  if (sc.family > 0.6) best.push('families');
  if (near_water) best.push('watching the water');
  return {
    indoor: !outdoor, outdoor, smoking: outdoor, shade: covered ? 'covered' : 'open air', near_water,
    noise: noise > 0.62 ? 'lively' : noise > 0.36 ? 'moderate' : 'quiet',
    privacy: t.zone === 'private' ? 'private room' : (sc.privacy || 0) > 0.7 ? 'semi-private' : 'open room',
    romantic: (sc.romantic || 0) > 0.72, family: (sc.family || 0) > 0.6, group: t.max_party >= 6,
    accessible: !!t.accessible, window: (sc.window_proximity || 0) > 0.6 && !outdoor, premium_view: !!t.premium_view,
    bar_m: Math.round((d.bar || 0) * u), kitchen_m: Math.round((d.kitchen || 0) * u), entrance_m: Math.round((d.entrance || 0) * u),
    water_m: Math.round(Math.max(0, (t.x - 62) * u)), best_for: best.slice(0, 4),
    seats: t.min_party + '\u2013' + t.max_party, zone_name: (zone && zone.name) || t.zone, setting: outdoor ? 'outdoors' : 'indoors',
  };
}

/** chips, grouped: setting / atmosphere / suitability */
export function chipsOf(a) {
  const setting = [a.setting === 'outdoors' ? 'Outdoors' : 'Indoors'];
  if (a.near_water) setting.push('Near the water');
  if (a.window) setting.push('By a window');
  setting.push(a.shade === 'covered' ? (a.outdoor ? 'Under an umbrella' : 'Under cover') : 'Open air');
  setting.push(a.smoking ? 'Smoking permitted' : 'Non-smoking');
  const atmosphere = [a.noise === 'quiet' ? 'Quiet' : a.noise === 'lively' ? 'Lively' : 'Moderate buzz'];
  atmosphere.push(a.privacy === 'private room' ? 'Private room' : a.privacy === 'semi-private' ? 'Semi-private' : 'Open room');
  if (a.premium_view) atmosphere.push('Premium view');
  const suits = [];
  if (a.romantic) suits.push('Romantic');
  if (a.family) suits.push('Family friendly');
  if (a.group) suits.push('Group table');
  if (a.accessible) suits.push('Step-free');
  return { setting, atmosphere, suits };
}

export function bestFor(a) {
  return a.best_for && a.best_for.length ? 'Best for ' + a.best_for.slice(0, 3).join(', ') + '.' : 'A solid all-round table.';
}

export const STATE_WORD = { AVAILABLE: 'Available', OCCUPIED: 'Occupied', RESERVED_SOON: 'Reserved soon', HELD: 'Being booked' };
