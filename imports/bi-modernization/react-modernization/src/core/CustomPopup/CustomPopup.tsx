import React from 'react';
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Typography,
  IconButton,
  Button,
  Grow,
  Divider,
  Box
} from '@mui/material';
import CloseIcon from '@mui/icons-material/Close';

const Transition = React.forwardRef(function Transition(props, ref) {
  return <Grow ref={ref} {...props} />;
});

const CustomPopup = ({
  open,
  onClose,
  title,
  titleStylings,
  message,
  showPrimaryButton = true,
  showSecondaryButton = true,
  primaryBtnText,
  secondaryBtnText,
  onPrimaryClick,
  onSecondaryClick,
  buttonSize = 'medium',
  disableBackdropClick = false,
  primaryBtnDisabled = false,
  popupWidth,
  popupbackgroundColor,
  primaryBtnSx,
  showCloseIcon = true,
  popupBackgroundImage = '',
  secondaryBtnSx
}) => {
  const handleClose = (event, reason) => {
    if (disableBackdropClick && (reason === 'backdropClick' || reason === 'escapeKeyDown')) {
      return;
    }
    onClose?.(event, reason);
  };

  return (
    <Dialog
      open={open}
      onClose={handleClose}
      TransitionComponent={Transition}
      transitionDuration={500}
      keepMounted
      maxWidth={false}
      fullWidth={false}
      aria-labelledby="custom-dialog-title"
      aria-describedby="custom-dialog-description"
      BackdropProps={{
        sx: {
          backgroundColor: 'transparent',
        },
      }}
      sx={{
        '& .MuiDialog-paper': {
          backgroundColor: popupbackgroundColor || 'ffffff',
          width: popupWidth || '600px',
          p: 2,
          position: 'relative',
          borderRadius: '24px',
          overflow: 'visible',
          backdropFilter: 'blur(160px)',
          boxshadow:' 0px 64px 64px -32px rgba(102, 37, 0, 0.56)'
        },
        '&.MuiDialog-root': {
          backgroundImage: `url(${popupBackgroundImage})`,
          backgroundSize: 'cover !important',
          backgroundPosition: 'center !important',
          minHeight: '100vh'
        },
      }}
    >
      {showCloseIcon && <IconButton
        onClick={(e) => onClose?.(e, 'iconClick')}
        aria-label="close"
        sx={{ position: 'absolute', top:15,  right: 25,color:'rgba(95, 125, 180, 1)' }}
        title="Close"
      >
        <CloseIcon />
      </IconButton>}

      <Box>
      <DialogTitle id="custom-dialog-title" sx={{ ...titleStylings, fontWeight: 'bold', paddingTop:'0px' }}>{title}</DialogTitle>
      <Divider sx={{ borderColor: 'rgba(0,0,0,0.12)' }} />
      </Box>
      <DialogContent dividers sx={{border:'none', overflow:'hidden'}}>
        {typeof message === 'string' ? (
          <Typography variant="body1">{message}</Typography>
        ) : (
          message
        )}
      </DialogContent>

      {(showPrimaryButton || showSecondaryButton) && (
        <DialogActions sx={{ justifyContent: 'flex-end',padding:0}}>
          {showSecondaryButton && (
            <Button  sx = {{...secondaryBtnSx,textTransform: 'capitalize', borderRadius:'28px',color:'linear-gradient(to bottom, #b31429 0%, #b31429 50%, #a0042b 50%, #a0042b 100%) !important'}} onClick={onSecondaryClick} size={buttonSize} variant="outlined">
              {secondaryBtnText}
            </Button>
          )}
          {showPrimaryButton && (
            <Button className='browseFileBtn' sx={{ ...primaryBtnSx,textTransform: 'capitalize', borderRadius:'28px',color:'white !important',marginRight:'15px'}} onClick={onPrimaryClick} size={buttonSize} variant="contained" disabled={primaryBtnDisabled}>
              {primaryBtnText}
            </Button>
          )}
        </DialogActions>
      )}
    </Dialog>
  );
};

export default CustomPopup;
