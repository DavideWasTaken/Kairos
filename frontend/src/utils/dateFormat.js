const DATE_ONLY_RE = /^(\d{4})-(\d{2})-(\d{2})$/;

const parseDateValue = (value) => {
  if (value === null || value === undefined || value === '') return null;
  if (value instanceof Date) {
    return Number.isNaN(value.getTime()) ? null : value;
  }
  if (typeof value === 'string') {
    const trimmed = value.trim();
    const m = DATE_ONLY_RE.exec(trimmed);
    if (m) {
      const year = Number(m[1]);
      const month = Number(m[2]);
      const day = Number(m[3]);
      const d = new Date(year, month - 1, day);
      return Number.isNaN(d.getTime()) ? null : d;
    }
    const d = new Date(trimmed);
    return Number.isNaN(d.getTime()) ? null : d;
  }
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? null : d;
};

export const formatDateShortIt = (value) => {
  const d = parseDateValue(value);
  if (!d) return value ?? '';
  return d.toLocaleDateString('it-IT', { day: '2-digit', month: '2-digit' });
};

export const formatDateIt = (value) => {
  const d = parseDateValue(value);
  if (!d) return value ?? '-';
  return d.toLocaleDateString('it-IT', { day: '2-digit', month: '2-digit', year: 'numeric' });
};

export const formatDateTimeIt = (value) => {
  const d = parseDateValue(value);
  if (!d) return value ?? '-';
  return d.toLocaleString('it-IT', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
};
