/** Keep ROM contest weights and unknown odds distinct from percentages. */
export function encounterChance(encounter) {
	if (encounter.encounterRate == null || encounter.rateKind === 'unknown') return 'Not fixed';
	if (encounter.rateKind === 'weight') return `${encounter.encounterRate} (weight)`;
	return `${encounter.encounterRate}%`;
}
