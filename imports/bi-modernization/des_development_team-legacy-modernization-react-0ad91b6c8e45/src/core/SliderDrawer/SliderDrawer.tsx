import React from 'react';
import {
    Drawer,
    Box,
    Typography,
    IconButton,
    Divider,
    Button
} from '@mui/material';
import CloseIcon from '@mui/icons-material/Close';

const SliderDrawer = ({
    open,
    onClose,
    title,
    width='22%',
    primaryBtnText='Save',
    secondaryBtnText = 'Cancel',
    onPrimaryClick,
    onSecondaryClick,
    children,
    disablePrimaryBtn = true,
    disableSecondaryBtn = true,
    disableSearch,
    titleStylings
}) => {
    return (
        <Drawer
         anchor='right'
         open={open}
         onClose = {onClose}
         transitionDuration={1000}
         PaperProps={
            {
                sx: {
                    width,
                    display:'flex',
                    flexDirection:'column',
                    height:'100vh',
                    borderTopLeftRadius:'28px',
                    borderBottomLeftRadius:'28px'
                }
            }
         }
         >
            <Box
              sx={{
                ...titleStylings,
                display:'flex',
                alignItems:'center',
                justifyContent:'space-between',
                px:2,
                py:1.5,
                borderBottom : '1px solid #ddd',
                zIndex:2000,
                background: 'linear-gradient(rgb(2, 10, 12) 0%, rgb(35, 61, 83) 60.1%, rgb(24, 43, 60) 100%)'

              }}>
                <Typography variant='h6' sx={{color:'white'}}>{title}</Typography>
                <IconButton onClick={onClose} title="Close">
                    <CloseIcon sx={{color:'white'}} />
                </IconButton>
            </Box>
            <Box
              sx={{
                flexGrow:'1',
                overflowY:'auto',
                background: 'rgba(231, 238, 248, 1)',
                px:2,
                py:2
              }}>
                 {children}
              </Box>
            <Box sx={{
                px:2,
                background: 'rgba(231, 238, 248, 1)',
                py:2,
                borderTop:'1px solid #ddd',
                display:'flex',
                justifyContent:'flex-end',
                gap:2,
                position:'sticky',
                bottom:0,
            }}
            >
           { disableSecondaryBtn && <Button variant='outlined' onClick={onSecondaryClick}>
                {secondaryBtnText}
            </Button>}
          { disablePrimaryBtn &&  <Button variant='contained' onClick={onPrimaryClick}>
                {primaryBtnText}
            </Button>}
            </Box>
        </Drawer>
    )
}

export default SliderDrawer;