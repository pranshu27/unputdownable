// import InfoIcon from '@mui/icons-material/Info';
// import ErrorIcon from '@mui/icons-material/Error';
// import CheckCircleIcon from '@mui/icons-material/CheckCircle';
// import Toaster from './core/Toaster/Toaster.tsx'

// <div style={{ padding: 24 }}>
//       <Button variant="outlined" onClick={() => showToast('info')}>
//         Show Info Toast
//       </Button>{' '}
//       <Button variant="outlined" onClick={() => showToast('success')}>
//         Show Success Toast
//       </Button>{' '}
//       <Button variant="outlined" onClick={() => showToast('error')}>
//         Show Error Toast
//       </Button>

//       <Toaster
//         open={toast.open}
//         onClose={handleClose}
//         title={toast.title}
//         message={toast.message}
//         icon={toast.icon}
//         severity={toast.severity}
//         duration={4000}
//       />


//     </div>


    //logic 

    //   const [toast, setToast] = useState({
    //     open: false,
    //     title: '',
    //     message: '',
    //     icon: null,
    //     severity: 'info',
    //   });
    
    //   const showToast = (type) => {
    //     const toastConfigs = {
    //       info: {
    //         title: 'Information',
    //         message: 'This is an info message.',
    //         icon: <InfoIcon fontSize="small" />,
    //         severity: 'info',
    //       },
    //       success: {
    //         title: 'Success',
    //         message: 'Your action was successful!',
    //         icon: <CheckCircleIcon fontSize="small" />,
    //         severity: 'success',
    //       },
    //       error: {
    //         title: 'Error',
    //         message: 'Something went wrong.',
    //         icon: <ErrorIcon fontSize="small" />,
    //         severity: 'error',
    //       },
    //     };
    
    //     setToast({ ...toastConfigs[type], open: true });
    //   };
    
    //   const handleClose = () => {
    //     setToast((prev) => ({ ...prev, open: false }));
    //   };
    