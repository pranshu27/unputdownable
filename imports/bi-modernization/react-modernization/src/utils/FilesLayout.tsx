import React from 'react';
import { Outlet } from 'react-router-dom';
import ChatWidget from '../core/ChatWidget.jsx';

/**
 * FilesLayout — used for the /files overview page.
 * NO sidebar, NO workspace nav. Full-width standalone layout.
 */
const FilesLayout = () => {
  return (
    <>
      <Outlet context={{ sideNavWidth: 0 }} />
      <ChatWidget />
    </>
  );
};

export default FilesLayout;
