import { createSlice, createAsyncThunk } from '@reduxjs/toolkit';
import yaml from 'js-yaml';

// Async thunk to load YAML config
export const fetchConfig = createAsyncThunk('config/fetchConfig', async () => {
  const response = await fetch('/config.yaml');
  const text = await response.text();
  const config = yaml.load(text);
  return config;
});

const configSlice = createSlice({
  name: 'config',
  initialState: {
    data: null,
    status: 'idle',
    error: null,
  },
  reducers: {},
  extraReducers: (builder) => {
    builder
      .addCase(fetchConfig.pending, (state) => {
        state.status = 'loading';
      })
      .addCase(fetchConfig.fulfilled, (state, action) => {
        state.status = 'succeeded';
        state.data = action.payload;
      })
      .addCase(fetchConfig.rejected, (state, action) => {
        state.status = 'failed';
        state.error = action.error.message;
      });
  }
});

export default configSlice.reducer;
