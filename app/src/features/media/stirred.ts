/**
 * The word the viewer and its chrome use for "the video on screen was touched".
 *
 * A video draws its own controls and the browser answers them; a phone keeps those taps to
 * itself and never tells the page. The window therefore hears nothing, and the buttons over
 * the picture would stay away. The viewer listens at the video element and says it here, where
 * the chrome is listening - one word, so neither side has to know about the other.
 */
export const STIRRED = 'muninn:stirred'
