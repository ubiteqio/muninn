import type { CapacitorConfig } from '@capacitor/cli'

const config: CapacitorConfig = {
  appId: 'de.muninn.app',
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
  plugins: {
    SplashScreen: {
      backgroundColor: '#0B0D12',
      showSpinner: false,
    },
  },
}

export default config
