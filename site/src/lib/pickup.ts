import pickupJson from '../data/pickup.json';
export const pickup = pickupJson as {
	activationPercent: number;
	bands: { min: number; max: number }[];
	items: { item: number; rates: number[] }[];
};

/** Merge adjacent level bands only when this item's chance is identical. */
export function pickupBands(item: number) {
	const rates = pickup.items.find(row => row.item === item)?.rates ?? [];
	const groups: { min: number; max: number; rate: number }[] = [];
	for (const [index, rate] of rates.entries()) {
		if (!rate) continue;
		const band = pickup.bands[index], previous = groups.at(-1);
		if (previous?.rate === rate && previous.max + 1 === band.min) previous.max = band.max;
		else groups.push({ ...band, rate });
	}
	return groups;
}
