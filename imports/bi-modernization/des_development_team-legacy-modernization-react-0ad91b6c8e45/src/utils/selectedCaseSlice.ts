import { createSlice, PayloadAction } from "@reduxjs/toolkit";

interface SelectedCaseState {
  value: string | null;
}

const initialState: SelectedCaseState = {
  value: localStorage.getItem("selectedCase") || null,
};

const selectedCaseSlice = createSlice({
  name: "selectedCase",
  initialState,
  reducers: {
    setSelectedCase(state, action: PayloadAction<string>) {
      state.value = action.payload;
      localStorage.setItem("selectedCase", action.payload);
    },
    clearSelectedCase(state) {
      state.value = null;
      localStorage.removeItem("selectedCase");
    }
  },
});

export const { setSelectedCase, clearSelectedCase } = selectedCaseSlice.actions;
export default selectedCaseSlice.reducer;
