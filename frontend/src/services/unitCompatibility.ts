/**
 * Mirrors `backend/app/services/unit_compatibility.py` — the backend is the
 * real enforcement authority (this is only a client-side UX helper to
 * offer a constrained unit picker instead of free text). Keep both in
 * sync if the canonical unit vocabulary ever changes.
 */
export interface UnitOption {
  value: string;
  label: string;
}

export const CANONICAL_UNITS: UnitOption[] = [
  { value: 'kg', label: 'Kilogramos (kg)' },
  { value: 'g', label: 'Gramos (g)' },
  { value: 'lb', label: 'Libras (lb)' },
  { value: 'oz', label: 'Onzas (oz)' },
  { value: 'L', label: 'Litros (L)' },
  { value: 'mL', label: 'Mililitros (mL)' },
  { value: 'GAL', label: 'Galones (gal)' },
  { value: 'unit', label: 'Unidad / pieza' },
  { value: 'dozen', label: 'Docena' },
  { value: 'case', label: 'Caja' },
];

const MASS_UNITS = new Set(['kg', 'g', 'lb', 'oz']);
const VOLUME_UNITS = new Set(['L', 'mL', 'GAL']);
const COUNT_UNITS = new Set(['unit', 'dozen', 'case']);

const ALLOWED_BY_CATALOG_UNIT: Record<string, Set<string>> = {
  kg: new Set([...MASS_UNITS, ...COUNT_UNITS]), // sólidos/al peso: masa o por unidad/pieza
  L: VOLUME_UNITS, // líquidos: solo volumen
  unit: COUNT_UNITS, // empacados discretos: solo por unidad/pieza
};

export function isUnitCompatible(catalogUnit: string | null, providedUnit: string): boolean {
  if (!catalogUnit) return true;
  const allowed = ALLOWED_BY_CATALOG_UNIT[catalogUnit];
  if (!allowed) return true;
  return allowed.has(providedUnit);
}

export function compatibleUnitsFor(catalogUnit: string | null): UnitOption[] {
  if (!catalogUnit) return CANONICAL_UNITS;
  const allowed = ALLOWED_BY_CATALOG_UNIT[catalogUnit];
  if (!allowed) return CANONICAL_UNITS;
  return CANONICAL_UNITS.filter((option) => allowed.has(option.value));
}
