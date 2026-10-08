import React from 'react';
import {
    AppBar,
    Toolbar,
    Box,
    Menu,
    MenuItem,
    Tooltip,
    IconButton,
    Paper,
    InputBase
} from '@mui/material';
import SearchIcon from '../../Assets/searchIcon.svg';

const Header = ({
    logo,
    logoContainerStyles,
    middleContent = null,
    rightIcons = [],
    expanded = true
}) => {
    const [anchorEl, setAnchorEl] = React.useState({});

    const handleMenuOpen = (event, index) => {
        setAnchorEl((prev) => ({ ...prev, [index]: event.currentTarget }));
    };

    const handleMenuClose = (index) => {
        setAnchorEl((prev) => ({ ...prev, [index]: null }));
    };

    return (
        <AppBar
            elevation={0}
            position="static"
            sx={{
                height: '68px',
                padding: '0 18px',
                background: 'transparent',
                color: 'black',
                boxShadow: 'none',
                border: 'none',
            }}
        >
            <Toolbar
                sx={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    width: '100%',
                    gap: 2,
                    padding: 0,
                    paddingRight: '0 !important',
                    minHeight: '68px !important',
                }}
            >
              { logo && <Box sx={{ display: 'flex', alignItems: 'center', minWidth: '160px' }}>
                    {logo && (
                        <Box sx={logoContainerStyles}>
                            {logo}
                        </Box>
                    )}
                </Box>}

                <Box
                    sx={{
                        flexGrow: 1,
                        display: 'flex',
                        justifyContent: 'flex-start',
                        paddingLeft:expanded ? '235px' : '60px',
                        minWidth: 0, 
                    }}
                >
                    <Box
                        sx={{
                            flex: 1,
                            maxWidth: '840px',
                            minWidth: '200px',
                        }}
                    >
                        {/* <Paper
                            component="form"
                            sx={{
                                p: '2px 20px',
                                display: 'flex',
                                alignItems: 'center',
                                width: '100%',
                                borderRadius: '999px',
                                backgroundColor: '#fffdfc',
                                border: '1px solid rgba(126, 113, 109, 0.18)',
                                boxShadow: '0 10px 30px rgba(76, 45, 43, 0.06)',
                                height:'46px'
                            }}
                        >
                            <InputBase
                                sx={{ ml: 1, flex: 1 }}
                                placeholder="Search"
                                inputProps={{ 'aria-label': 'search' }}
                            />
                              {/* <IconButton sx={{ p: '10px' }} aria-label="search">
                                <SearchIcon sx={{ color: 'rgba(235, 23, 0, 1)' }} />
                            </IconButton> */}
                            {/* <img src={SearchIcon} alt="Search" />
                        </Paper>  */}
                        
                    </Box>
                </Box>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    {rightIcons.map((item, index) => (
                        <React.Fragment key={index}>
                            <Tooltip title={item.tooltip || ''}>
                                <IconButton
                                    sx={{
                                        '&:hover': { backgroundColor: 'transparent' },
                                    }}
                                    onClick={
                                        item.menuItems
                                            ? (e) => handleMenuOpen(e, index)
                                            : item.onClick
                                    }
                                >
                                    {item.icon}
                                </IconButton>
                            </Tooltip>
                            {item.menuItems && (
                                <Menu
                                    anchorEl={anchorEl[index]}
                                    open={Boolean(anchorEl[index])}
                                    onClose={() => handleMenuClose(index)}
                                >
                                    {item.menuItems.map((menu, i) => (
                                        <MenuItem key={i} onClick={menu.onClick}>
                                            {menu.label}
                                        </MenuItem>
                                    ))}
                                </Menu>
                            )}
                        </React.Fragment>
                    ))}
                </Box>
            </Toolbar>
        </AppBar>
    );
};

export default Header;
