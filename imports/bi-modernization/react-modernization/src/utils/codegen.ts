import { createSlice } from "@reduxjs/toolkit";

const initialState = {
  code: null,
  testCasesCode : null,
  ETLdata : null,
  selectedBoard : null,
  selectedPlatform: null,
  ticketKey: null,
  userInfo : {
    username:'',
    password:'',
    baseUrl:'',
    server:'',
    project:'',
  }
};

const codeGenSlice = createSlice({
  name: 'codeGen',
  initialState,
  reducers: {
    storeCode(state, action) {
      state.code = action.payload;
    },

    storeUserInfo(state,action) {
        state.userInfo = action.payload;
    },

    storeTestCasesCode(state,action){
      state.testCasesCode=action.payload
    },

    storeETL(state,action){
      state.ETLdata=action.payload  
    },

    storeSelectedBoard(state, action){
      state.selectedBoard = action.payload;
    },

    storeSelectedPlatform(state, action){
      state.selectedPlatform = action.payload;
    },

    storeTicketKey(state, action) {
      state.ticketKey = action.payload;
    }

  },
});

export const { storeCode,storeUserInfo,storeTestCasesCode,storeETL,storeSelectedBoard, storeSelectedPlatform, storeTicketKey } = codeGenSlice.actions;
export default codeGenSlice.reducer;
