/// <reference types="vite/client" />

/** Public base path the app is served under ("/" in dev, "/charon/dolly/" when deployed). Always ends with "/". */
export const BASE: string = import.meta.env.BASE_URL;

/** Router basename: no trailing slash, undefined at the site root. */
export const ROUTER_BASENAME: string | undefined = BASE === "/" ? undefined : BASE.replace(/\/$/, "");

/** Absolute path of an evaluator API route, e.g. apiPath("versions") -> "/charon/dolly/api/versions". */
export const apiPath = (route: string) => `${BASE}api/${route}`;
