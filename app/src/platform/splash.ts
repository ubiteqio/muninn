import { Capacitor } from '@capacitor/core'
import { SplashScreen } from '@capacitor/splash-screen'

/**
 * Take the native launch image away once the app is on screen.
 *
 * iOS shows the launch screen until somebody says otherwise, and "otherwise" is this call. The
 * app has its own quiet waiting screen for the moment while the session is restored; without
 * this, that moment is spent behind a picture that never goes away.
 */
export async function hideNativeSplash(): Promise<void> {
  if (!Capacitor.isNativePlatform()) return

  try {
    await SplashScreen.hide()
  } catch {
    // Nothing to hide, then.
  }
}
