// Colsubsidio Brand Theme — Reto Piscilago 30x
// All colors must be sourced from this file. Never use ad-hoc hex values.

export const colors = {
  primary: {
    yellow: '#ffd000', // Pantone 109 C
    blue: '#0067b1',   // Pantone 2196 C
  },
  neutral: {
    grafito: '#575756', // Pantone Cool Gray 11 C — tercer color oficial Colsubsidio (LogosCorp/Colores Oficiales.png)
    grafito80: '#797978',
    grafito60: '#9a9a9a',
    grafito40: '#bcbcbb',
  },
  flag: {
    threshold: '#dc2626',
    trend: '#ea580c',
    both: '#7c3aed',
  },
  traffic: {
    red: '#ef4444',
    yellow: '#ffd000',
    green: '#22c55e',
  },
  ui: {
    background: '#ffffff',
    surface: '#f8f9fa',
    textPrimary: '#1a1a2e',
    textSecondary: '#6b7280',
    border: '#e5e7eb',
    success: '#22c55e',
    error: '#dc2626',
  },
} as const;

// Touch targets — CLAUDE.md §4: minimum 48×48px for all interactive elements
export const touchTargets = {
  minimum: 48,    // px
  voiceButton: 120, // px — VoiceButton is the primary affordance
} as const;

export const typography = {
  fontFamily: '"Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
  sizes: {
    base: '1rem',      // 16px — body text
    large: '1.125rem', // 18px — item names in ConfirmDialog
    quantity: '1.5rem', // 24px bold — quantities visible from distance
    label: '0.875rem', // 14px — secondary labels
  },
} as const;

// Logos oficiales — fuente: LogosCorp/ (fuera del repo). Servidos como estáticos desde /public/brand.
export const logos = {
  // Marca ícono (tangram amarillo) — usar sobre fondos claros/blancos.
  iconYellow: '/brand/logo-icon-yellow.png',
  // Lockup completo "Colsubsidio" en blanco — SOLO sobre fondos oscuros/de color (azul, grafito). Invisible sobre blanco.
  fullWhite: '/brand/logo-full-white.png',
} as const;
