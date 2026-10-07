import type { CapacitorConfig } from '@capacitor/cli'

const config: CapacitorConfig = {
  appId: 'io.ubiteq.apps.muninn',
  appName: 'Muninn',
  webDir: 'dist',
  // The native app talks to the server over HTTPS and sends its tokens in the header; it never
  // relies on cookies, so no server URL is baked in here.
  ios: {
    contentInset: 'never',
    backgroundColor: '#0B0D12',
  },
  android: {
    backgroundColor: '#0B0D12',
  },
  server: {
    // Android serves the app from https://localhost unless told otherwise, and a page loaded
    // over HTTPS may not ask a server in the house over plain HTTP: every sign-in was blocked
    // as mixed content before it left the device. http://localhost is the origin the server
    // lets in, and still counts as secure, so the Keystore and crypto keep working. iOS has
    // its own scheme and is not touched by this.
    androidScheme: 'http',
  },
  plugins: {
    SplashScreen: {
      backgroundColor: '#0B0D12',
      showSpinner: false,
    },
    // While Muninn is open the bell updates live; a banner on top would say the same twice.
    PushNotifications: {
      presentationOptions: [],
    },
  },
}

export default config
