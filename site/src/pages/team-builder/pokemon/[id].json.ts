import { species, areas, items, moves } from '../../../lib/data';
import { formChanges } from '../../../lib/verified-mechanics';
import { createPlannerData } from '../../../lib/team-builder-data.mjs';

export function getStaticPaths() {
  return species.map(mon => ({ params: { id: String(mon.id) }, props: { id: mon.id } }));
}
const planner = createPlannerData({ species, areas, items, moves, formChanges });
export function GET({ props }: { props: { id: number } }) {
  return new Response(JSON.stringify(planner.detail(props.id)), { headers: { 'Content-Type': 'application/json' } });
}
