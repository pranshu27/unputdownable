import React, { useState, useEffect } from 'react';
import { Box, Avatar, Typography, Button, TextField } from '@mui/material';
import NotificationsIcon from '@mui/icons-material/Notifications';
import SettingsIcon from '@mui/icons-material/Settings';
import InfoIcon from '@mui/icons-material/Info';
import LogoutIcon from '@mui/icons-material/Logout';
import HomeIcon from '@mui/icons-material/Home';
import Header from '../../core/Header/Header.tsx';
import SideNav from '../../core/SideNav/SideNav.tsx';
import ContentCard from '../../core/CardContent/CardContent.tsx';
import CustomPagination from '../../core/CustomPagination/CustomPagination.tsx';
import DynamicForm from '../../core/DynamicForm/DynamicForm.tsx';
import Loader from '../../core/Loader/Loader.tsx';
import { useApiWithLoader } from '../../Hooks/useApiWithLoder.js';
import SliderDrawer from '../../core/SliderDrawer/SliderDrawer.tsx';
import CustomPopup from '../../core/CustomPopup/CustomPopup.tsx';
import ErrorIcon from '@mui/icons-material/Error';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import Toaster from '../../core/Toaster/Toaster.tsx';
import EditIcon from '@mui/icons-material/Edit';
import DeleteIcon from '@mui/icons-material/Delete';
import DataTable from '../../core/DataTable/DataTable.tsx';
import SaveIcon from '@mui/icons-material/Save';
import CancelIcon from '@mui/icons-material/Cancel';
import ReusableCard from '../../core/Card/Card.tsx';
import ReactQuill from 'react-quill';
import 'react-quill/dist/quill.snow.css';

import { sanitizeToHTML } from '../../utils/SanitizeAndRender.tsx';


const formConfig = [
  {
    type:'default',
    value:'abc',
    label:'Some random'
  },
   {
    type:'default',
    value:'abcdef',
    label:'Some random text'
  },
  {
    type: "text",
    name: "name",
    label: "Name",
    placeholder: "Enter your name",
    required: true,
    minLength: 3,
    maxLength: 30,
    fieldWidth: "48%",
  },
  {
    type: "email",
    name: "email",
    label: "Email",
    placeholder: "Enter your email",
    required: true,
    pattern: "^[^\\s@]+@[^\\s@]+\\.[^\\s@]+$",
    fieldWidth: "48%",
  },
  {
    type: "number",
    name: "age",
    label: "Age",
    placeholder: "Enter your age",
    min: 18,
    max: 100,
    fieldWidth: "48%",
  },
  {
    type: "select",
    name: "gender",
    label: "Gender",
    required: true,
    options: ["Male", "Female", "Other"],
    fieldWidth: "48%",
  },
  {
    type: "multiselect",
    name: "hobbies",
    label: "Hobbies",
    options: ["Reading", "Gaming", "Cooking", "Music"],
    fieldWidth: "48%",
  },
  {
    type: "file",
    name: "resume",
    label: "Upload Resume",
    accept: ".pdf,.doc,.docx",
    required: true,
    fieldWidth: "48%",
  },
];


const  CoreComponents = () => {
      const [isExpanded, setIsExpanded] = useState(false);
      const sideNavWidth = isExpanded ? 120 : 60;
    
      const rightIcons = [
        {
          icon: <NotificationsIcon />,
          tooltip: 'Notifications',
          onClick: () => alert('notifications click'),
        },
        {
          icon: <SettingsIcon />,
          tooltip: 'Settings',
          menuItems: [
            { label: 'Preferences', onClick: () => alert('Preferences clicked') },
            { label: 'System Settings', onClick: () => alert('System Settings clicked') },
          ],
        },
        {
          icon: <Avatar alt="user" src="/static/images/avatar/1.jpg" />,
          tooltip: 'Profile',
          menuItems: [
            { label: 'My Profile', onClick: () => alert('My Profile') },
            { label: 'Logout', onClick: () => alert('Logout clicked') },
          ],
        },
      ];
    
      const topNavItems = [
        { icon: <HomeIcon />, label: 'Home', onClick: () => alert('Go Home') },
        { icon: <SettingsIcon />, label: 'Settings', onClick: () => alert('Settings') },
      ];
    
      const bottomNavItems = [
        { icon: <InfoIcon />, label: 'About', onClick: () => alert('About') },
        { icon: <LogoutIcon />, label: 'Logout', onClick: () => alert('Logout') },
      ];
    
    
      //pagination
    
    
      const [page, setPage] = useState(0); 
      const [rowsPerPage, setRowsPerPage] = useState(10);
    
      const totalRecords = 137; // fetched from API or static
    
      const handleChangePage = (event, newPage) => {
        setPage(newPage);
      };
    
      const handleChangeRowsPerPage = (event) => {
        setRowsPerPage(parseInt(event.target.value, 10));
        setPage(0);
      };
    
      //pagination ends here
    
      //form
    
      const [formData, setFormData] = useState({});
      const [errors, setErrors] = useState({});
    
      const handleChange = (name, value) => {
        setFormData((prev) => ({ ...prev, [name]: value }));
        setErrors((prev) => ({ ...prev, [name]: null }));
      };
    
      const validateForm = () => {
        const newErrors = {};
        formConfig.forEach((field) => {
          const value = formData[field.name];
          if (field.required && !value) {
            newErrors[field.name] = "This field is required";
          } else if (
            field.pattern &&
            value &&
            !new RegExp(field.pattern).test(value)
          ) {
            newErrors[field.name] = "Invalid format";
          } else if (field.minLength && value?.length < field.minLength) {
            newErrors[field.name] = `Minimum ${field.minLength} characters`;
          } else if (field.maxLength && value?.length > field.maxLength) {
            newErrors[field.name] = `Maximum ${field.maxLength} characters`;
          }
        });
        setErrors(newErrors);
        return Object.keys(newErrors).length === 0;
      };
    
      const handleSubmit = () => {
        if (validateForm()) {
          console.log("✅ Final Form Data:", formData);
        }
      };
    
      const handleReset = () => {
        setFormData({});
        setErrors({});
      };
    
      //form ends here
    
    
      //loader
      const { callApi, loading } = useApiWithLoader();
      const [data, setData] = useState([]);
      useEffect(() => {
        const fetchData = async () => {
          try {
            const result = await callApi({
              url: "https://jsonplaceholder.typicode.com/posts",
              method: "GET",
            });
            setData(result);
          } catch (err) {
            console.error("API error", err);
          }
        };
        fetchData();
    
      }, []);
      //Loader ends here
    
    
      //slider
    
      const [openDrawer, setOpenDrawer] = useState(false);
    
      const handleOpen = () => setOpenDrawer(true);
      const handleClose = () => setOpenDrawer(false);
    
      const handleSave = () => {
        handleClose();
      }
    
      const handleCancel = () => {
        handleClose();
      }
    
    
      //slider close here
    
    
      //Popup
    
    
      const [openPopup, setOpenPopup] = useState(false);
    
      const handlePopupOpen = () => setOpenPopup(true);
      const handlePopupClose = () => setOpenPopup(false);
    
      const handlePrimaryAction = () => {
        handlePopupClose();
      }
    
      const handleSecondaryAction = () => {
        handlePopupClose();
      }
    
      //popup ends here!!!
    
    
      //toaster
    
      const [toast, setToast] = useState({
        open: false,
        title: '',
        message: '',
        icon: null,
        severity: 'info',
      });
    
      const showToast = (type) => {
        const toastConfigs = {
          info: {
            title: 'Information',
            message: 'This is an info message.',
            icon: <InfoIcon fontSize="small" />,
            severity: 'info',
          },
          success: {
            title: 'Success',
            message: 'Your action was successful!',
            icon: <CheckCircleIcon fontSize="small" />,
            severity: 'success',
          },
          error: {
            title: 'Error',
            message: 'Something went wrong.',
            icon: <ErrorIcon fontSize="small" />,
            severity: 'error',
          },
        };
    
        setToast({ ...toastConfigs[type], open: true });
      };
    
      const handleToasterClose = () => {
        setToast((prev) => ({ ...prev, open: false }));
      };
    
      //toaster ends here!!
    
    
      //Table
    
      const columns = [
        { field: 'id', headerName: 'ID' },
        { field: 'name', headerName: 'Name' },
        { field: 'age', headerName: 'Age' },
        { field: 'role', headerName: 'Role' },
        { field: 'email', headerName: 'Email' },
        { field: 'phone', headerName: 'Phone' },
        { field: 'department', headerName: 'Department' },
        { field: 'location', headerName: 'Location' },
        { field: 'status', headerName: 'Status' },
        { field: 'startDate', headerName: 'Start Date' },
        { field: 'salary', headerName: 'Salary' },
        { field: 'manager', headerName: 'Manager' },
        { field: 'lastLogin', headerName: 'Last Login' },
        { field: 'performance', headerName: 'Performance' },
        { field: 'projects', headerName: 'Projects' },
      ];
    
      const initialRows = [
        {
          id: 1,
          name: 'John Doe',
          age: 32,
          role: 'Admin',
          email: 'john.doe@example.com',
          phone: '123-456-7890',
          department: 'IT',
          location: 'New York',
          status: 'Active',
          startDate: '2020-01-15',
          salary: '$90,000',
          manager: 'Jane Smith',
          lastLogin: '2025-06-01 10:15',
          performance: 'Excellent',
          projects: 5,
        },
        {
          id: 2,
          name: 'Jane Smith',
          age: 28,
          role: 'User',
          email: 'jane.smith@example.com',
          phone: '234-567-8901',
          department: 'HR',
          location: 'Chicago',
          status: 'Active',
          startDate: '2019-07-10',
          salary: '$75,000',
          manager: 'Mike Johnson',
          lastLogin: '2025-06-05 09:45',
          performance: 'Good',
          projects: 3,
        },
        {
          id: 3,
          name: 'Mike Johnson',
          age: 45,
          role: 'Manager',
          email: 'mike.johnson@example.com',
          phone: '345-678-9012',
          department: 'Finance',
          location: 'Boston',
          status: 'Active',
          startDate: '2018-03-20',
          salary: '$110,000',
          manager: 'Sara Connor',
          lastLogin: '2025-06-04 14:30',
          performance: 'Outstanding',
          projects: 7,
        },
        {
          id: 4,
          name: 'Alice Brown',
          age: 29,
          role: 'User',
          email: 'alice.brown@example.com',
          phone: '456-789-0123',
          department: 'Marketing',
          location: 'Seattle',
          status: 'Inactive',
          startDate: '2021-05-22',
          salary: '$65,000',
          manager: 'John Doe',
          lastLogin: '2025-05-25 12:00',
          performance: 'Average',
          projects: 2,
        },
        {
          id: 5,
          name: 'Bob White',
          age: 38,
          role: 'Admin',
          email: 'bob.white@example.com',
          phone: '567-890-1234',
          department: 'IT',
          location: 'Austin',
          status: 'Active',
          startDate: '2017-11-11',
          salary: '$95,000',
          manager: 'Jane Smith',
          lastLogin: '2025-06-06 08:20',
          performance: 'Good',
          projects: 6,
        },
        {
          id: 6,
          name: 'Carol Green',
          age: 33,
          role: 'User',
          email: 'carol.green@example.com',
          phone: '678-901-2345',
          department: 'Sales',
          location: 'Denver',
          status: 'Active',
          startDate: '2022-02-28',
          salary: '$70,000',
          manager: 'Mike Johnson',
          lastLogin: '2025-06-03 11:15',
          performance: 'Excellent',
          projects: 4,
        },
        {
          id: 7,
          name: 'David Lee',
          age: 41,
          role: 'Manager',
          email: 'david.lee@example.com',
          phone: '789-012-3456',
          department: 'Operations',
          location: 'San Francisco',
          status: 'Active',
          startDate: '2016-08-14',
          salary: '$105,000',
          manager: 'Sara Connor',
          lastLogin: '2025-06-07 09:50',
          performance: 'Outstanding',
          projects: 8,
        },
        {
          id: 8,
          name: 'Eva Adams',
          age: 27,
          role: 'User',
          email: 'eva.adams@example.com',
          phone: '890-123-4567',
          department: 'HR',
          location: 'Miami',
          status: 'Active',
          startDate: '2020-12-01',
          salary: '$68,000',
          manager: 'John Doe',
          lastLogin: '2025-06-02 10:40',
          performance: 'Good',
          projects: 3,
        },
        {
          id: 9,
          name: 'Frank Moore',
          age: 35,
          role: 'Admin',
          email: 'frank.moore@example.com',
          phone: '901-234-5678',
          department: 'IT',
          location: 'New York',
          status: 'Inactive',
          startDate: '2019-04-19',
          salary: '$92,000',
          manager: 'Jane Smith',
          lastLogin: '2025-05-30 15:10',
          performance: 'Average',
          projects: 5,
        },
        {
          id: 10,
          name: 'Grace Kim',
          age: 30,
          role: 'User',
          email: 'grace.kim@example.com',
          phone: '012-345-6789',
          department: 'Finance',
          location: 'Chicago',
          status: 'Active',
          startDate: '2021-06-07',
          salary: '$72,000',
          manager: 'Mike Johnson',
          lastLogin: '2025-06-06 14:55',
          performance: 'Good',
          projects: 4,
        },
      ];
    
    
      const [rows, setRows] = useState(initialRows);
      const [editRowId, setEditRowId] = useState(null);
      const [editedData, setEditedData] = useState({});
    
      const actions = (row) => {
        const isEditing = editRowId === row.id;
    
        if (isEditing) {
          return [
            { key: 'save', label: 'Save', icon: <SaveIcon /> },
            { key: 'cancel', label: 'Cancel', icon: <CancelIcon /> },
          ];
        }
        return [
          { key: 'edit', label: 'Edit', icon: <EditIcon /> },
          { key: 'delete', label: 'Delete', icon: <DeleteIcon /> },
        ];
      };
    
      const handleAction = (key, row) => {
        if (key === 'edit') {
          setEditRowId(row.id);
          setEditedData(row);
        } else if (key === 'cancel') {
          setEditRowId(null);
          setEditedData({});
        } else if (key === 'save') {
          const updatedRows = rows.map((r) => (r.id === row.id ? editedData : r));
          setRows(updatedRows);
          setEditRowId(null);
          setEditedData({});
          console.log('Updated Table Data:', updatedRows);
        } else if (key === 'delete') {
          const updatedRows = rows.filter((r) => r.id !== row.id);
          setRows(updatedRows);
        }
      };
    
      const handleRowSelect = (selectedIds) => {
        console.log('Selected Rows:', selectedIds);
      };
      const handleEditChange = (field, value) => {
        setEditedData((prev) => ({ ...prev, [field]: value }));
      };
    
      //Table ends here!!
    
      //Reusable Card edit
    
      const handleCardEdit = () => {
        console.log('Edit clicked');
      };
    
      const handleCardDelete = () => {
        console.log('Delete clicked');
      };
    
        const sampleForm = (
        <Box component="form" display='flex' flexDirection="column" gap={2}>
          <DynamicForm
            config={formConfig}
            formData={formData}
            errors={errors}
            onChange={handleChange}
            onSubmit={handleSubmit}
            onReset={handleReset}
            showSubmitButton={false}
            showResetButton={false}
            submitText="Submit"
            resetText="Clear"
            inputSize="small"
            layout="horizontal"
          />
    
            <DataTable
                data={rows}
                columns={columns}
                showCheckbox={true}
                actions={actions}
                onActionClick={handleAction}
                onRowSelect={handleRowSelect}
                editRowId={editRowId}
                editedData={editedData}
                onEditChange={handleEditChange}
              />
        </Box>
      );
    
    
      // Reusbale card ends here!!
    
    
      const toolbarOptions = [
      ['bold', 'italic', 'underline', 'strike'],        // B I U S
      ['blockquote', 'code-block'],                     // Quotes, Code
      [{ 'list': 'ordered' }, { 'list': 'bullet' }],    // Lists
      [{ 'header': [1, 2, 3, false] }],                  // Headings
      [{ 'color': [] }, { 'background': [] }],          // Font/Background color
      [{ 'align': [] }],                                // Alignment
      ['clean']                                         // Clear formatting
    ];
    
    const modules = {
      toolbar: toolbarOptions
    };
    
    const formats = [
      'bold', 'italic', 'underline', 'strike',
      'blockquote', 'code-block',
      'list', 'bullet',
      'header',
      'color', 'background',
      'align'
    ];
    
     const [content, setContent] = useState(`<h3><strong>Executive Summary:</strong></h3>
      <p>This is a <strong>sample summary</strong> showing how <em>rich formatting</em> can be applied using a WYSIWYG editor. You can <u>underline</u>, <s>strike</s>, highlight, align text, and more.</p>
      <ul>
        <li>Supports bullet and numbered lists</li>
        <li>Allows inline <code>code</code> blocks</li>
        <li>Text <span style="color:red;">color</span> and <span style="background-color:yellow;">highlight</span></li>
      </ul>`);
    
      const handleQuillSave = () => {
        localStorage.setItem('editorData', content);
        alert("Content saved!");
      };
    
        const [value, setValue] = useState('');
    
    
        //marker
    
         const dummyMarkdown = `
         **Executive Summary: Advanced Data Processing and Integration Using Alteryx**\n\nThis executive summary presents a detailed analysis of the data processing and integration workflow executed through Alteryx, focusing on optimizing sales and operational data for strategic insights. The workflow efficiently integrates complex data sources, applies sophisticated transformations, and generates comprehensive outputs to support business decision-making.\n\n**Data Sources:**\nThe workflow utilizes a primary data source:\n- **ODBC: Hana Prod**: This source extracts sales and line totals at the delivery-note level for the past three months, supporting OCT_TOD, Terms and Conditions applications, and ad-hoc analysis. The data is refreshed monthly and includes critical fields such as sales order date, billing date, plant, distribution channel, financial class, and various transaction and fee amounts.\n\n**Key Transformations:**\n1. **Dynamic Input**:\n   - Modifies SQL queries to extract data for different weeks, ensuring timely and relevant data aggregation.\n\n2. **DateTime Conversion**:\n   - Standardizes date formats for consistency across datasets.\n\n3. **Field Selection and Renaming**:\n   - Utilizes the **Select** tool to streamline data fields, enhancing clarity and usability.\n\n4. **Custom Calculations**:\n   - Implements complex calculations such as Rush Order Fee and Total Shipping and Handling, using mathematical expressions to derive actionable metrics.\n\n5. **Data Integration**:\n   - Employs **Join** and **Union** tools to merge datasets, creating a cohesive data environment for analysis.\n\n6. **Data Filtering and Renaming**:\n   - Applies filters to exclude null values, ensuring data integrity, and dynamically renames fields to remove prefixes for cleaner outputs.\n\n**Outputs:**\n- **CSV File Output**: The final processed data is stored in a CSV format, providing a comprehensive dataset for further analysis. Key fields include sales order date, billing date, distribution channel details, financial metrics, and various calculated fees and charges.\n\n**Business Value:**\nThe Alteryx workflow delivers substantial business benefits by:\n- **Enhancing Data Quality**: Ensures data accuracy and consistency, vital for reliable analysis and reporting.\n- **Improving Operational Efficiency**: Automates complex data preparation tasks, reducing manual effort and speeding up data processing.\n- **Supporting Strategic Decision-Making**: Provides stakeholders with detailed, actionable insights to guide both strategic planning and operational decisions.\n\nThis summary encapsulates the strategic objectives and outcomes of the Alteryx-based data processing workflow, highlighting its critical role in driving business efficiency and informed decision-making.
    `;
     const safeHtml = sanitizeToHTML(dummyMarkdown, 'markdown');
    
     return (
         <>
              {loading && (
                <Box
                  sx={{
                    position: "fixed",
                    top: 0,
                    left: 0,
                    width: "100vw",
                    height: "100vh",
                    backgroundColor: "#ffffff",
                    display: "flex",
                    justifyContent: "center",
                    alignItems: "center",
                    zIndex: 1300,
                  }}
                >
                  <Loader show={loading} />
                </Box>
        
        
              )}
        
              <Box>
                {/* <Header
                  logo={<Typography variant="h6">Logo</Typography>}
                  middleContent={<Typography variant="body1">Middle Section to include functionality </Typography>}
                  rightIcons={rightIcons}
                />
        
                <SideNav
                  topNavItems={topNavItems}
                  bottomNavItems={bottomNavItems}
                  showExpandToggle={true}
                  initialExpanded={false}
                  onToggleExpanded={setIsExpanded}
                /> */}
        
                <ContentCard
                  heading={<Typography variant="h6">Search Results</Typography>}
                  sideNavWidth={isExpanded ? 120 : 60}
                  bottomContent={
                    <CustomPagination
                      count={totalRecords}
                      page={page}
                      rowsPerPage={rowsPerPage}
                      onPageChange={handleChangePage}
                      onRowsPerPageChange={handleChangeRowsPerPage}
                    />
                  }
                >
                  {/* Form html code starts here*/}
                  <DynamicForm
                    config={formConfig}
                    formData={formData}
                    errors={errors}
                    onChange={handleChange}
                    onSubmit={handleSubmit}
                    onReset={handleReset}
                    showSubmitButton={true}
                    showResetButton={true}
                    submitText="Submit"
                    resetText="Clear"
                    inputSize="small"
                    layout="horizontal"
                  />
        
                  {/* form html code ends here */}
        
                  {/* slider code starts here */}
                  <Button variant='contained' onClick={handleOpen} >
                    Open Slider Drawer
                  </Button>
        
        
                  <SliderDrawer
                    open={openDrawer}
                    onClose={handleClose}
                    title="User Form"
                    onPrimaryClick={handleSave}
                    onSecondaryClick={handleCancel}
                    primaryBtnText='Submit'
                    secondaryBtnText='Back'
                    width='35%'
                  >{sampleForm}</SliderDrawer>
        
                  {/* slider code ends here */}
        
                  {/* Popup starts here */}
        
                  <Button sx={{ marginLeft: '10px' }} variant='contained' onClick={handlePopupOpen}>
                    Open Popup
                  </Button>
        
        
                  <CustomPopup
                    open={openPopup}
                    onClose={handlePopupClose}
                    title="Confirm Action"
                    message="Are you sure you want to perform this action?"
                    primaryBtnText='Confirm'
                    secondaryBtnText='Cancel'
                    onPrimaryClick={handlePrimaryAction}
                    onSecondaryClick={handleSecondaryAction}
                    buttonSize='medium'>
                  </CustomPopup>
        
                  {/* popup ends here!!!!! */}
        
                  {/* {Toaster starts here} */}
        
                  <Button sx={{ marginLeft: '10px' }} variant="outlined" onClick={() => showToast('info')}>
                    Show Info Toast
                  </Button>{' '}
                  <Button sx={{ marginLeft: '10px' }} variant="outlined" onClick={() => showToast('success')}>
                    Show Success Toast
                  </Button>{' '}
                  <Button sx={{ marginLeft: '10px' }} variant="outlined" onClick={() => showToast('error')}>
                    Show Error Toast
                  </Button>
        
        
                  <Toaster
                    open={toast.open}
                    onClose={handleToasterClose}
                    title={toast.title}
                    message={toast.message}
                    icon={toast.icon}
                    severity={toast.severity}
                    duration={4000}
                  />
        
                  {/* Toaster ends here */}
        
                  {/* Table */}
                  <DataTable
                    data={rows}
                    columns={columns}
                    showCheckbox={true}
                    actions={actions}
                    onActionClick={handleAction}
                    onRowSelect={handleRowSelect}
                    editRowId={editRowId}
                    editedData={editedData}
                    onEditChange={handleEditChange}
                  />
                  {/* Table ends here */}
        
                  {/* Reusable Card Start here */}
                  <ReusableCard
                    width={300}
                    height={200}
                    headingLabel="Dynamic"
                    description="his is a sample description for the user profile.his is a sample description for the user profile.his is a sample description for the user profile.his is a sample description for the user profile.his is a sample description for the user profile.This is a sample description for the user profile. It might be very long and should be ellipsized."
                    buttons={[
                      {
                        label: 'Edit',
                        backgroundRequired: false,
                        outlineRequired: true,
                        color: 'primary',
                        onClick: () => console.log('Edit clicked'),
                      },
                      {
                        label: 'Delete',
                        backgroundRequired: true,
                        outlineRequired: false,
                        color: 'error',
                        onClick: () => console.log('Delete clicked'),
                      },
                      {
                        label: 'View',
                        backgroundRequired: false,
                        outlineRequired: false,
                        color: 'secondary',
                        onClick: () => console.log('View clicked'),
                      },
                    ]}
                  />
                  {/*reusable card ends here */}
        
                   <ReactQuill
                value={content}
                onChange={setContent}
                modules={modules}
                formats={formats}
                theme="snow"
                style={{ minHeight: '300px' }}
              />
              <button
                style={{ marginTop: '10px', padding: '10px 20px', cursor: 'pointer' }}
                onClick={handleQuillSave}
              >
                Save
              </button>
        
               <div dangerouslySetInnerHTML={{ __html: safeHtml }} />
        
                </ContentCard>
        
              </Box>
            </>
     )
} 

export default CoreComponents


//  headerActions={[
       
//         <Tooltip title="Delete" key="delete">
//           <IconButton onClick={handleDelete}>
//             <DeleteIcon />
//           </IconButton>
//         </Tooltip>
//         <Button variant="contained" onClick={() => alert('Action')}>
//           Custom Action
//         </Button>,
//       ] }