import { trainers } from './data';
import { buildTrainerProfiles } from './trainer-encounters.mjs';

export const { profiles: trainerProfiles, byId: trainerProfileById } = buildTrainerProfiles(trainers);
