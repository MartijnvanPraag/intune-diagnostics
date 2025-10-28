import { Configuration, PopupRequest } from "@azure/msal-browser";

/**
 * MSAL Configuration for OAuth 2.0 Authorization Code Flow with PKCE
 * 
 * This configuration uses your Entra App for authentication WITHOUT storing any secrets.
 * The PKCE (Proof Key for Code Exchange) flow is used for Single-Page Applications.
 */

// Entra App Client ID (no secret required!)
export const msalConfig: Configuration = {
  auth: {
    clientId: "fbadc585-90b3-48ab-8052-c1fcc32ce3fe", // Your Entra App ID
    authority: "https://login.microsoftonline.com/72f988bf-86f1-41af-91ab-2d7cd011db47", // Microsoft tenant (single-tenant)
    redirectUri: window.location.origin, // Automatically uses current origin
    postLogoutRedirectUri: window.location.origin,
  },
  cache: {
    cacheLocation: "localStorage", // Store tokens in localStorage (persists across sessions)
    storeAuthStateInCookie: false, // Set to true if you have IE11/Edge issues
  },
  system: {
    loggerOptions: {
      logLevel: process.env.NODE_ENV === 'development' ? 3 : 1, // Verbose in dev, errors only in prod
      loggerCallback: (level, message, containsPii) => {
        if (containsPii) return;
        switch (level) {
          case 0: // Error
            console.error(message);
            break;
          case 1: // Warning
            console.warn(message);
            break;
          case 2: // Info
            console.info(message);
            break;
          case 3: // Verbose
            console.debug(message);
            break;
        }
      },
    },
  },
};

/**
 * Scopes for login request
 * These are the permissions your app needs from Microsoft Graph
 */
export const loginRequest: PopupRequest = {
  scopes: [
    "User.Read", // Read user profile
    "openid",    // Required for OIDC
    "profile",   // Get user name
    "email",     // Get user email
  ],
};

/**
 * Scopes for accessing your backend API
 * If you exposed an API scope in Entra App, use it here
 */
export const apiRequest = {
  scopes: [
    `api://fbadc585-90b3-48ab-8052-c1fcc32ce3fe/access_as_user`, // Your custom API scope (if configured)
  ],
};

/**
 * Microsoft Graph API endpoint
 */
export const graphConfig = {
  graphMeEndpoint: "https://graph.microsoft.com/v1.0/me",
};
