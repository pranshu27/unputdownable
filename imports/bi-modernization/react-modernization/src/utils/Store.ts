
import { configureStore } from '@reduxjs/toolkit';
import apiDataReducer from './DataSlice.ts';
import formReducer from './formSlice.ts';
import jiraformReducer from './jiraslice.ts';
import codeGenReducer from './codegen.ts';
import configReducer from './configSlice';
import selectedCaseReducer from "./selectedCaseSlice.ts";
import jobTrackerReducer from './jobTrackerSlice.ts';


export const store = configureStore({
  reducer: {
    apiData: apiDataReducer,
    form: formReducer, 
    jira: jiraformReducer,
    codeGen : codeGenReducer,
    selectedCase: selectedCaseReducer,
    jobTracker: jobTrackerReducer,
    // config: configReducer
  },
});
export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;
