import { createSlice } from '@reduxjs/toolkit';

const formSlice = createSlice({
  name: 'form',
  initialState: {
    selectedFile: null,
    etlTool: '',
    model: '',
    technology:'',
    framework:''
  },
  reducers: {
    setFormData: (state, action) => {
      const { filename, etlTool, model,technology,framework } = action.payload;
      state.selectedFile = filename;
      state.etlTool = etlTool;
      state.model = model;
      state.technology = technology;
      state.framework = framework
    }
  }
});

export const { setFormData } = formSlice.actions;
export default formSlice.reducer;
