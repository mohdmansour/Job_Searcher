import { readFileSync } from 'node:fs'

/**
 * Browser tests run signed in as one Clerk test account (see global.setup.ts). The app pages
 * check the account on the server, so a signed-out browser only ever sees the sign-in page.
 */
export const AUTH_FILE = 'e2e/.auth/user.json'
export const USER_ID_FILE = 'e2e/.auth/user-id.txt'

/** Read when a test runs, not when the file loads: the setup project writes it first. */
export const testUserId = () => readFileSync(USER_ID_FILE, 'utf8').trim()

/** Browser data as the site stores it for the signed-in test account. */
export const owned = (data: object) => JSON.stringify({ ...data, owner: testUserId() })

/** For tests about a visitor who isn't signed in. */
export const signedOut = { storageState: { cookies: [], origins: [] } }
