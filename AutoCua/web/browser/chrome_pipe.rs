
use serde_json::{json, Value};

/// Encode a browser-level download policy request for CDP pipe transport.
pub fn download_policy_request(id: u64, deny: bool) -> Vec<u8> {
    let request = json!({
        "id": id,
        "method": "Browser.setDownloadBehavior",
        "params": {
            "behavior": if deny { "deny" } else { "default" },
            "eventsEnabled": deny,
        }
    });

    let mut frame = serde_json::to_vec(&request)
        .expect("Fixed CDP request must serialize");
    frame.push(0);
    frame
}

/// Return true only for a successful reply to the expected command.
/// Browser events without an id are not command acknowledgments.
pub fn check_policy_reply(frame: &[u8], expected_id: u64) -> Result<bool, String> {
    let reply: Value = serde_json::from_slice(frame)
        .map_err(|e| format!("Invalid CDP response: {e}"))?;

    let Some(id) = reply.get("id") else {
        return Ok(false);
    };

    if id.as_u64() != Some(expected_id) {
        return Err("Unexpected CDP response identifier".into());
    }
    if let Some(error) = reply.get("error") {
        return Err(format!("Chrome rejected download protection: {error}"));
    }
    if !reply.get("result").is_some_and(Value::is_object) {
        return Err("Missing download protection acknowledgment".into());
    }

    Ok(true)
}


#[cfg(windows)]
pub struct ChromePipes {
    pub command_write: std::fs::File,
    pub response_read: std::fs::File,
    child_read: std::os::windows::io::OwnedHandle,
    child_write: std::os::windows::io::OwnedHandle,
}

#[cfg(windows)]
impl ChromePipes {
    pub fn new() -> std::io::Result<Self> {
        use std::os::windows::io::{AsRawHandle, FromRawHandle, OwnedHandle, RawHandle};
        use windows_sys::Win32::Foundation::{
            SetHandleInformation, HANDLE, HANDLE_FLAG_INHERIT,
        };
        use windows_sys::Win32::Security::SECURITY_ATTRIBUTES;
        use windows_sys::Win32::System::Pipes::CreatePipe;

        fn pair() -> std::io::Result<(OwnedHandle, OwnedHandle)> {
            let attributes = SECURITY_ATTRIBUTES {
                nLength: std::mem::size_of::<SECURITY_ATTRIBUTES>() as u32,
                lpSecurityDescriptor: std::ptr::null_mut(),
                bInheritHandle: 1,
            };
            let mut read = std::mem::MaybeUninit::<HANDLE>::uninit();
            let mut write = std::mem::MaybeUninit::<HANDLE>::uninit();

            if unsafe {
                CreatePipe(read.as_mut_ptr(), write.as_mut_ptr(), &attributes, 0)
            } == 0 {
                return Err(std::io::Error::last_os_error());
            }

            // SAFETY: CreatePipe succeeded and initialized both owned handles.
            Ok(unsafe {
                (
                    OwnedHandle::from_raw_handle(read.assume_init() as RawHandle),
                    OwnedHandle::from_raw_handle(write.assume_init() as RawHandle),
                )
            })
        }

        let (child_read, parent_write) = pair()?;
        let (parent_read, child_write) = pair()?;

        // Only the Chrome ends may be inherited by the Chrome process.
        for handle in [&parent_write, &parent_read] {
            if unsafe {
                SetHandleInformation(
                    handle.as_raw_handle() as HANDLE,
                    HANDLE_FLAG_INHERIT,
                    0,
                )
            } == 0 {
                return Err(std::io::Error::last_os_error());
            }
        }

        Ok(Self {
            command_write: parent_write.into(),
            response_read: parent_read.into(),
            child_read,
            child_write,
        })
    }

    pub fn chrome_argument(&self) -> String {
        use std::os::windows::io::AsRawHandle;

        format!(
            "--remote-debugging-io-pipes={},{}",
            self.child_read.as_raw_handle() as usize,
            self.child_write.as_raw_handle() as usize,
        )
    }

    /// Call only after Chrome has inherited its two pipe handles.
    pub fn into_parent_ends(self) -> (std::fs::File, std::fs::File) {
        (self.command_write, self.response_read)
    }
}


#[cfg(windows)]
pub struct ChromeHandleList {
    // The process attribute buffer must be suitably aligned.
    storage: Vec<usize>,
    // Keep the handle array at a stable address until process creation.
    handles: Box<[windows_sys::Win32::Foundation::HANDLE; 2]>,
}

#[cfg(windows)]
impl ChromeHandleList {
    pub fn new(pipes: &ChromePipes) -> std::io::Result<Self> {
        use std::os::windows::io::AsRawHandle;
        use windows_sys::Win32::Foundation::HANDLE;
        use windows_sys::Win32::System::Threading::{
            InitializeProcThreadAttributeList,
            UpdateProcThreadAttribute,
            PROC_THREAD_ATTRIBUTE_HANDLE_LIST,
        };

        let mut bytes = 0usize;

        // First call obtains the required buffer size.
        unsafe {
            InitializeProcThreadAttributeList(
                std::ptr::null_mut(),
                1,
                0,
                &mut bytes,
            );
        }

        if bytes == 0 {
            return Err(std::io::Error::last_os_error());
        }

        let word_size = std::mem::size_of::<usize>();
        let words = bytes.div_ceil(word_size);

        let mut storage = vec![0usize; words];
        let pointer = storage.as_mut_ptr() as _;

        if unsafe {
            InitializeProcThreadAttributeList(
                pointer,
                1,
                0,
                &mut bytes,
            )
        } == 0 {
            return Err(std::io::Error::last_os_error());
        }

        let mut list = Self {
            storage,
            handles: Box::new([
                pipes.child_read.as_raw_handle() as HANDLE,
                pipes.child_write.as_raw_handle() as HANDLE,
            ]),
        };

        let attribute_pointer = list.as_mut_ptr();

        let result = unsafe {
            UpdateProcThreadAttribute(
                attribute_pointer,
                0,
                PROC_THREAD_ATTRIBUTE_HANDLE_LIST as usize,
                list.handles.as_mut_ptr() as _,
                std::mem::size_of_val(&*list.handles),
                std::ptr::null_mut(),
                std::ptr::null_mut(),
            )
        };

        if result == 0 {
            let error = std::io::Error::last_os_error();
            drop(list);
            return Err(error);
        }

        Ok(list)
    }

    pub fn as_mut_ptr(
        &mut self,
    ) -> windows_sys::Win32::System::Threading::LPPROC_THREAD_ATTRIBUTE_LIST {
        self.storage.as_mut_ptr() as _
    }
}

#[cfg(windows)]
impl Drop for ChromeHandleList {
    fn drop(&mut self) {
        use windows_sys::Win32::System::Threading::DeleteProcThreadAttributeList;

        // SAFETY: The attribute list was successfully initialized.
        unsafe {
            DeleteProcThreadAttributeList(self.as_mut_ptr());
        }
    }
}



#[cfg(windows)]
pub struct ChromePipeTransport {
    command_write: std::fs::File,
    response_read: std::fs::File,
    pending: Vec<u8>,
    next_id: u64,
}

#[cfg(windows)]
impl ChromePipeTransport {
    pub fn new(pipes: ChromePipes) -> Self {
        let (command_write, response_read) = pipes.into_parent_ends();

        Self {
            command_write,
            response_read,
            pending: Vec::new(),
            next_id: 0,
        }
    }

    /// Require a positive browser-level CDP acknowledgment.
    /// No acknowledgment means no permission to navigate.
    pub fn set_downloads_denied(&mut self, deny: bool) -> Result<(), String> {
        use std::io::{Read, Write};
        use std::os::windows::io::AsRawHandle;
        use std::time::{Duration, Instant};
        use windows_sys::Win32::Foundation::HANDLE;
        use windows_sys::Win32::System::Pipes::PeekNamedPipe;

        self.next_id = self.next_id.checked_add(1)
            .ok_or("CDP request identifier exhausted")?;
        let id = self.next_id;

        self.command_write
            .write_all(&download_policy_request(id, deny))
            .map_err(|e| format!("Cannot send Chrome download policy: {e}"))?;

        let deadline = Instant::now() + Duration::from_secs(10);

        loop {
            // A CDP pipe may contain events before the command's response.
            while let Some(end) = self.pending.iter().position(|byte| *byte == 0) {
                let frame: Vec<u8> = self.pending.drain(..=end).collect();

                if check_policy_reply(&frame[..frame.len() - 1], id)? {
                    return Ok(());
                }
            }

            if Instant::now() >= deadline {
                return Err(
                    "Chrome did not acknowledge download protection".into()
                );
            }

            let mut available = 0u32;
            let ok = unsafe {
                PeekNamedPipe(
                    self.response_read.as_raw_handle() as HANDLE,
                    std::ptr::null_mut(),
                    0,
                    std::ptr::null_mut(),
                    &mut available,
                    std::ptr::null_mut(),
                )
            };

            if ok == 0 {
                return Err(format!(
                    "Chrome CDP pipe unavailable: {}",
                    std::io::Error::last_os_error()
                ));
            }

            if available == 0 {
                std::thread::sleep(Duration::from_millis(10));
                continue;
            }

            let mut chunk = [0u8; 4096];
            let count = chunk.len().min(available as usize);

            let received = self.response_read
                .read(&mut chunk[..count])
                .map_err(|e| format!("Chrome CDP read failed: {e}"))?;

            if received == 0 {
                return Err("Chrome closed its CDP pipe".into());
            }

            self.pending.extend_from_slice(&chunk[..received]);

            if self.pending.len() > 1024 * 1024 {
                return Err("Chrome CDP response exceeded size limit".into());
            }
        }
    }
}


#[cfg(windows)]
fn quote_windows_argument(argument: &str) -> String {
    if !argument.is_empty()
        && !argument.chars().any(|c| c.is_whitespace() || c == '"')
    {
        return argument.to_owned();
    }

    let mut quoted = String::from("\"");
    let mut backslashes = 0;

    for character in argument.chars() {
        match character {
            '\\' => backslashes += 1,
            '"' => {
                quoted.extend(std::iter::repeat('\\').take(backslashes * 2 + 1));
                quoted.push('"');
                backslashes = 0;
            }
            _ => {
                quoted.extend(std::iter::repeat('\\').take(backslashes));
                quoted.push(character);
                backslashes = 0;
            }
        }
    }

    quoted.extend(std::iter::repeat('\\').take(backslashes * 2));
    quoted.push('"');
    quoted
}

/// Launch Chrome with only its two CDP pipe handles inherited.
/// The caller retains ownership of the pipes and must keep the transport
/// alive for the duration of the scoped session.
#[cfg(windows)]
pub fn spawn_chrome_with_explicit_pipes(
    executable: &std::path::Path,
    arguments: &[String],
    pipes: &ChromePipes,
) -> std::io::Result<u32> {
    use std::ffi::OsStr;
    use std::os::windows::ffi::OsStrExt;
    use windows_sys::Win32::Foundation::CloseHandle;
    use windows_sys::Win32::System::Threading::{
        CreateProcessW, PROCESS_INFORMATION, STARTUPINFOEXW,
        CREATE_NEW_PROCESS_GROUP, DETACHED_PROCESS,
        EXTENDED_STARTUPINFO_PRESENT,
    };

    if !executable.is_absolute()
        || arguments.iter().any(|argument| argument.contains('\0'))
        || executable.as_os_str().encode_wide().any(|unit| unit == 0)
    {
        return Err(std::io::Error::new(
            std::io::ErrorKind::InvalidInput,
            "Chrome requires an absolute executable and valid arguments",
        ));
    }

    let mut handle_list = ChromeHandleList::new(pipes)?;

    let executable_wide: Vec<u16> = executable
        .as_os_str()
        .encode_wide()
        .chain(std::iter::once(0))
        .collect();

    let command_line = std::iter::once(
        executable.to_string_lossy().into_owned()
    )
    .chain(arguments.iter().cloned())
    .map(|argument| quote_windows_argument(&argument))
    .collect::<Vec<_>>()
    .join(" ");

    let mut command_wide: Vec<u16> = OsStr::new(&command_line)
        .encode_wide()
        .chain(std::iter::once(0))
        .collect();

    // SAFETY: These Windows structures permit zero initialization.
    let mut startup: STARTUPINFOEXW = unsafe { std::mem::zeroed() };
    startup.StartupInfo.cb = std::mem::size_of::<STARTUPINFOEXW>() as u32;
    startup.lpAttributeList = handle_list.as_mut_ptr();

    let mut process: PROCESS_INFORMATION = unsafe { std::mem::zeroed() };

    let created = unsafe {
        CreateProcessW(
            executable_wide.as_ptr(),
            command_wide.as_mut_ptr(),
            std::ptr::null(),
            std::ptr::null(),
            1, // Inheritance is restricted by the explicit handle list.
            EXTENDED_STARTUPINFO_PRESENT
                | CREATE_NEW_PROCESS_GROUP
                | DETACHED_PROCESS,
            std::ptr::null(),
            std::ptr::null(),
            &startup.StartupInfo,
            &mut process,
        )
    };

    if created == 0 {
        return Err(std::io::Error::last_os_error());
    }

    let process_id = process.dwProcessId;

    unsafe {
        CloseHandle(process.hThread);
        CloseHandle(process.hProcess);
    }

    Ok(process_id)
}

#[cfg(windows)]
impl ChromePipeTransport {
    pub fn load_unpacked_extension(
        &mut self,
        path: &std::path::Path,
    ) -> Result<String, String> {
        use std::io::{Read, Write};
        use std::os::windows::io::AsRawHandle;
        use std::time::{Duration, Instant};
        use windows_sys::Win32::Foundation::HANDLE;
        use windows_sys::Win32::System::Pipes::PeekNamedPipe;

        if !path.is_absolute() || !path.is_dir() {
            return Err("Extension directory must exist and be absolute".into());
        }
        let path = path.to_str()
            .ok_or("Extension directory is not valid Unicode")?;

        self.next_id = self.next_id.checked_add(1)
            .ok_or("CDP request identifier exhausted")?;
        let request_id = self.next_id;

        let mut request = serde_json::to_vec(&json!({
            "id": request_id,
            "method": "Extensions.loadUnpacked",
            "params": { "path": path }
        }))
        .map_err(|e| e.to_string())?;
        request.push(0);

        self.command_write.write_all(&request)
            .map_err(|e| format!("Cannot send extension load request: {e}"))?;

        let deadline = Instant::now() + Duration::from_secs(15);

        loop {
            while let Some(end) = self.pending.iter().position(|&b| b == 0) {
                let frame: Vec<u8> = self.pending.drain(..=end).collect();
                let reply: Value = serde_json::from_slice(
                    &frame[..frame.len() - 1]
                ).map_err(|e| format!("Invalid CDP response: {e}"))?;

                let Some(id) = reply.get("id") else {
                    continue; // Ignore unsolicited browser events.
                };
                if id.as_u64() != Some(request_id) {
                    return Err("Unexpected CDP response identifier".into());
                }
                if let Some(error) = reply.get("error") {
                    return Err(format!("Chrome refused extension loading: {error}"));
                }

                let extension_id = reply.pointer("/result/id")
                    .and_then(Value::as_str)
                    .ok_or("Chrome did not return an extension ID")?;

                if extension_id.len() != 32
                    || !extension_id.bytes().all(|b| (b'a'..=b'p').contains(&b))
                {
                    return Err("Chrome returned an invalid extension ID".into());
                }

                return Ok(extension_id.to_owned());
            }

            if Instant::now() >= deadline {
                return Err("Chrome did not acknowledge extension loading".into());
            }

            let mut available = 0u32;
            let ok = unsafe {
                PeekNamedPipe(
                    self.response_read.as_raw_handle() as HANDLE,
                    std::ptr::null_mut(),
                    0,
                    std::ptr::null_mut(),
                    &mut available,
                    std::ptr::null_mut(),
                )
            };
            if ok == 0 {
                return Err(format!(
                    "Chrome CDP connection lost: {}",
                    std::io::Error::last_os_error()
                ));
            }
            if available == 0 {
                std::thread::sleep(Duration::from_millis(10));
                continue;
            }

            let mut chunk = [0u8; 4096];
            let count = chunk.len().min(available as usize);
            let received = self.response_read.read(&mut chunk[..count])
                .map_err(|e| format!("Chrome CDP read failed: {e}"))?;

            if received == 0 {
                return Err("Chrome closed its CDP connection".into());
            }

            self.pending.extend_from_slice(&chunk[..received]);
            if self.pending.len() > 1024 * 1024 {
                return Err("Chrome CDP response exceeded size limit".into());
            }
        }
    }
}



#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn deny_request_uses_browser_domain_and_null_framing() {
        let frame = download_policy_request(7, true);
        assert_eq!(frame.last(), Some(&0));

        let request: Value =
            serde_json::from_slice(&frame[..frame.len() - 1]).unwrap();

        assert_eq!(request["id"], 7);
        assert_eq!(request["method"], "Browser.setDownloadBehavior");
        assert_eq!(request["params"]["behavior"], "deny");
        assert_eq!(request["params"]["eventsEnabled"], true);
    }

    #[test]
    fn success_requires_an_exact_acknowledgment() {
        assert_eq!(
            check_policy_reply(br#"{"id":7,"result":{}}"#, 7),
            Ok(true)
        );
        assert_eq!(
            check_policy_reply(br#"{"method":"Browser.downloadProgress"}"#, 7),
            Ok(false)
        );
        assert!(check_policy_reply(br#"{"id":8,"result":{}}"#, 7).is_err());
        assert!(check_policy_reply(
            br#"{"id":7,"error":{"message":"Denied"}}"#, 7
        ).is_err());
    }


    #[cfg(windows)]
    #[test]
    fn child_pipe_ends_are_inheritable_but_parent_ends_are_private() {
        use std::os::windows::io::AsRawHandle;
        use windows_sys::Win32::Foundation::{
            GetHandleInformation, HANDLE, HANDLE_FLAG_INHERIT,
        };

        fn inheritable(handle: HANDLE) -> bool {
            let mut flags = 0u32;
            let result = unsafe { GetHandleInformation(handle, &mut flags) };
            assert_ne!(result, 0, "Cannot inspect Windows handle");
            flags & HANDLE_FLAG_INHERIT != 0
        }

        let pipes = ChromePipes::new().expect("Cannot create Chrome pipes");

        assert!(inheritable(pipes.child_read.as_raw_handle() as HANDLE));
        assert!(inheritable(pipes.child_write.as_raw_handle() as HANDLE));

        assert!(!inheritable(pipes.command_write.as_raw_handle() as HANDLE));
        assert!(!inheritable(pipes.response_read.as_raw_handle() as HANDLE));
    }

    #[cfg(windows)]
    #[test]
    fn explicit_chrome_handle_list_can_be_initialized() {
        let pipes = ChromePipes::new().unwrap();
        let _list = ChromeHandleList::new(&pipes).unwrap();
    }


    #[cfg(windows)]
    #[test]
    #[ignore = "Internal helper for the inherited pipe test"]
    fn inherited_pipe_child() {
        use std::io::{Read, Write};
        use std::os::windows::io::{FromRawHandle, RawHandle};

        let specification = std::env::var("SACCADE_TEST_PIPE_HANDLES")
            .expect("Missing child pipe handles");

        let handles = specification
            .strip_prefix("--remote-debugging-io-pipes=")
            .expect("Invalid pipe argument");

        let (read, write) = handles.split_once(',')
            .expect("Expected two pipe handles");

        let read: usize = read.parse().unwrap();
        let write: usize = write.parse().unwrap();

        // SAFETY: The parent explicitly inherited these handles into
        // this child process. This test owns and closes its copies.
        let mut input = unsafe {
            std::fs::File::from_raw_handle(read as RawHandle)
        };
        let mut output = unsafe {
            std::fs::File::from_raw_handle(write as RawHandle)
        };

        let mut request = Vec::new();

        loop {
            let mut byte = [0u8; 1];
            input.read_exact(&mut byte).unwrap();
            if byte[0] == 0 {
                break;
            }
            request.push(byte[0]);
            assert!(request.len() < 4096);
        }

        let message: serde_json::Value =
            serde_json::from_slice(&request).unwrap();

        assert_eq!(
            message["method"],
            "Browser.setDownloadBehavior"
        );
        assert_eq!(message["params"]["behavior"], "deny");

        let response = serde_json::json!({
            "id": message["id"],
            "result": {}
        });

        output.write_all(response.to_string().as_bytes()).unwrap();
        output.write_all(&[0]).unwrap();
        output.flush().unwrap();
    }

    #[cfg(windows)]
    #[test]
    fn explicitly_inherited_pipes_exchange_cdp_messages() {
        let pipes = ChromePipes::new().unwrap();

        std::env::set_var(
            "SACCADE_TEST_PIPE_HANDLES",
            pipes.chrome_argument(),
        );

        let executable = std::env::current_exe().unwrap();

        let arguments = vec![
            "--exact".to_string(),
            "chrome_pipe::tests::inherited_pipe_child".to_string(),
            "--ignored".to_string(),
        ];

        let launched = spawn_chrome_with_explicit_pipes(
            &executable,
            &arguments,
            &pipes,
        );

        std::env::remove_var("SACCADE_TEST_PIPE_HANDLES");

        let process_id = launched.expect(
            "Could not launch the isolated child process"
        );

        assert_ne!(process_id, 0);

        let mut transport = ChromePipeTransport::new(pipes);

        transport.set_downloads_denied(true).expect(
            "Child process did not receive or acknowledge CDP"
        );
    }


    #[cfg(windows)]
    #[test]
    #[ignore = "Launches real Chrome with an isolated test profile"]
    fn real_chrome_acknowledges_browser_download_denial() {
        use std::path::PathBuf;
        use std::time::{SystemTime, UNIX_EPOCH};

        let root = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
        let test_dir = root.join("../../.cache/platform-session/chrome-pipe-test");

        std::fs::create_dir_all(&test_dir).unwrap();

        let unique = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();

        let profile = test_dir.join(format!(
            "profile-{}-{unique}",
            std::process::id()
        ));

        // Stage the real extension inside this isolated test profile.
        let source = root.join("browser/AutoCuaBridge");
        let staged = crate::stage_bridge::stage(
            &source,
            &profile.join(".saccade-bridge"),
        )
        .expect("Could not stage the test extension");

        let pipes = ChromePipes::new().unwrap();

        let process_id = crate::bridge::launch_chrome_with_pipes(
            &profile,
            &pipes,
        )
        .unwrap_or_else(|_| {
            panic!("Could not launch isolated Chrome");
        });

        assert_ne!(process_id, 0);

        let mut transport = ChromePipeTransport::new(pipes);

        // Downloads must be denied before loading AutoCuaBridge.
        transport
            .set_downloads_denied(true)
            .expect("Chrome did not acknowledge download denial");

        // Load the real staged extension through the private browser CDP pipe.
        let loaded_id = transport
            .load_unpacked_extension(&staged)
            .expect("Chrome did not load AutoCuaBridge");

        assert_eq!(
            loaded_id,
            crate::stage_bridge::extension_id(&staged),
            "Chrome loaded an unexpected extension identity"
        );

        // Restore the download policy at the end of this isolated test.
        transport
            .set_downloads_denied(false)
            .expect("Chrome did not acknowledge policy restoration");

        use windows_sys::Win32::Foundation::{
            CloseHandle, WAIT_OBJECT_0,
        };
        use windows_sys::Win32::System::Threading::{
            OpenProcess, WaitForSingleObject,
        };

        // SYNCHRONIZE: permission to wait for this exact child process.
        let chrome_process = unsafe {
            OpenProcess(0x0010_0000, 0, process_id)
        };

        assert_ne!(chrome_process, 0, "Cannot inspect test Chrome process");

        // Losing the private debugging pipe must terminate test Chrome.
        drop(transport);

        let exit_status = unsafe {
            WaitForSingleObject(chrome_process, 15_000)
        };

        unsafe {
            CloseHandle(chrome_process);
        }

        assert_eq!(
            exit_status,
            WAIT_OBJECT_0,
            "Test Chrome did not exit after its private CDP pipe closed"
        );

    }



}
