import { gradients, logos } from '../../theme';

/**
 * The one piece of chrome that's identical on every screen, authenticated
 * or not — logo + brand, nothing else. Previously this only existed as
 * Login's local `BrandHeader`; every other screen folded its own title
 * into the same blue bar as its actions (`PageHeader`), so there was no
 * single "this is always here" anchor across the whole app. `OptionsRibbon`
 * (rendered directly below this) is the one that changes per screen.
 * `position: sticky` so it — and the ribbon below it — stay visible while
 * scrolling a long item list, matching "cinta azul fija" literally.
 */
export function BrandRibbon() {
  return (
    <div
      style={{
        position: 'sticky',
        top: 0,
        zIndex: 101,
        background: gradients.brandBlue,
        padding: '10px 24px',
        display: 'flex',
        justifyContent: 'center',
      }}
    >
      <img src={logos.fullWhite} alt="Colsubsidio" style={{ height: 26 }} />
    </div>
  );
}
