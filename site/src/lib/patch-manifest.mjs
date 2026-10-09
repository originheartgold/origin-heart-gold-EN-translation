/** Validate the small public release manifest before enabling downloads. */
export function isPatchManifest(value) {
  return value !== null && typeof value === 'object'
    && value.available !== false
    && typeof value.tag === 'string' && /^v\d+\.\d+\.\d+(?:-rc\d+)?$/.test(value.tag)
    && typeof value.file === 'string' && /^[A-Za-z0-9._-]+\.xdelta$/.test(value.file)
    && Number.isSafeInteger(value.size) && value.size > 0
    && typeof value.patched_sha1 === 'string' && /^[0-9a-f]{40}$/i.test(value.patched_sha1)
    && (value.prerelease === undefined || typeof value.prerelease === 'boolean')
    && (value.release_url === undefined || typeof value.release_url === 'string' && /^https:\/\//.test(value.release_url));
}
