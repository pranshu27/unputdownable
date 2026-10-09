import { normalizeId } from './normalize';

export const getNormalizedModel = (model: any) => {
  return {
    ...model,

    tables: model.tables.map((t: any) => ({
      ...t,
      normalized_id: normalizeId(t.id),
    })),

    relationships: model.relationships.map((rel: any) => ({
      ...rel,
      left_normalized: normalizeId(rel.left_table_id),
      right_normalized: normalizeId(rel.right_table_id),
    })),
  };
};