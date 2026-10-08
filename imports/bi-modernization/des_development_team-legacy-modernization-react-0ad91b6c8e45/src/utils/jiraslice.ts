import { createSlice } from '@reduxjs/toolkit';

const jiraSlice =  createSlice({
   name:'jira',
    initialState: {
        username:'',
        token:'',
        baseUrl:'',
        server:'',
        project:'',
    },
    reducers: {
       setJiraformData(state,action) {
          const response = action.payload;
          state.username = response.username;
          state.token = response.token;
          state.baseUrl = response.baseUrl;
          state.server = response.server;
          state.project = response.project;
       } 
    }
})

export const {setJiraformData} = jiraSlice.actions;
export default jiraSlice.reducer;