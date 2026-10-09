import React from 'react';
import { Outlet } from 'react-router-dom';
import ChatWidget from '../core/ChatWidget.jsx';

const Layout = ({ sideNavWidth }) => {
  return (
    <>
      <Outlet context={{ sideNavWidth }} />
      <ChatWidget />
    </>
  );
};

export default Layout;
