export const normalizeId = (id: string | null | undefined) => {
    if (!id) return '';
  
    return id
      .toLowerCase()
      .replace('tbl_', '')
      .replace(/\s+/g, '_')
      .replace(/[^a-z0-9_]/g, '');
  };