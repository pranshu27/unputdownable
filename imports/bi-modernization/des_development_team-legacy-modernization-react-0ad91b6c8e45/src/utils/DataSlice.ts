import { createSlice, PayloadAction } from '@reduxjs/toolkit';

interface ApiDataState {
  data: any;
}

const initialState: ApiDataState = {
  data: null,
};

const apiDataSlice = createSlice({
  name: 'apiData',
  initialState,
  reducers: {
    setApiData(state, action: PayloadAction<any>) {
      state.data = action.payload;
    },
     updateExecutiveSummary(state, action: PayloadAction<string>) {
      if (state.data) {
        state.data = {
          ...state.data,
          executivesummary: action.payload,
        };
      }
      localStorage.setItem('analyzeResponse', JSON.stringify(state.data));
    },
  },
});

export const { setApiData, updateExecutiveSummary } = apiDataSlice.actions;
export default apiDataSlice.reducer;
