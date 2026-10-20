# Enhancing the delay in the listener when there is exception in the connection

https://github.com/microsoft/azure-pipelines-agent/pull/5448 (merged 2026-02-18)

### **Context**

Adding a delay in the Agent listener code before retrying request when there is a retriable exception thrown from the server side.



Related work-item: [AB#2338439](https://dev.azure.com/mseng/b924d696-3eae-4116-8443-9a18392d8544/_workitems/edit/2338439)



---



### **Description**

When the server is unavailable (not an authentication error), the server returns a different exception (e.g., VssServiceResponseException with status code 404). The agent continuously retries the request indefinitely. Each retry invokes the OAuth token provisioning mechanism on the server (the server checks whether there is any cached token or not else it creates one). This behavior significantly increases load on an already unavailable server.

Hence we have increased the Backoff delay in the agent code before retrying the requests. **We have implemented an exponential backoff delay which is capped at 5 minutes** and all the changes are behind a Feature flag so that the execution can be controlled.





---



### **Risk Assessment** (Low / Medium / High)  

Low



---



### **Unit Tests Added or Updated** (Yes / No)  

Yes added L0 test cases for the delay behaviour in 3 methods CreateSessionAsync, GetNextMessageAsync and KeepAlive based on the state of the feature flag added.



---



### **Additional Testing Performed**

Manually tested connecting the agent with devfabric and then stopping the tfs devfabric web service. The agent delayed the request based on the continuous error count.



**For the main listener loop:**

- Exponential backoff delay for attempts<8:

<img width="1920" height="252" alt="image" src="https://github.com/user-attachments/assets/5e502cd5-0d89-4996-9e61-8aaa866f668c" />



- When the attempt number>=8 the delay is capped at 5 minutes(300 seconds):

<img width="1942" height="308" alt="image" src="https://github.com/user-attachments/assets/981161af-950a-4a9b-b8f6-c6ec61a060aa" />







**For the Keep Alive Call:**

- Exponential backoff delay for attempts<8:

<img width="1619" height="119" alt="image" src="https://github.com/user-attachments/assets/9c7f0b0b-9a1b-4c7a-8995-d10bf582a39d" />



- When the attempt number>=8 the delay is capped at 5 minutes(300 seconds):

<img width="1733" height="115" alt="image" src="https://github.com/user-attachments/assets/34e3a8e4-3f76-48b0-9f31-513ffe4ad69e" />



**For Create Session Call:**

 [when there is session conflict]

- Exponential backoff delay for attempts<8:

<img width="1137" height="139" alt="image" src="https://github.com/user-attachments/assets/00132920-8d3c-4ca9-b6a9-4158c9bc4bcc" />



- As soon as the retry limit is reached the session creation attempt will stop:

<img width="1703" height="162" alt="image" src="https://github.com/user-attachments/assets/89020069-31c5-45c2-a1dc-4a2dcd586f1b" />









--- 



### **Change Behind Feature Flag** (Yes / No)

No



---



### **Tech Design / Approach**

This is done to reduce the load on the server where the agent continuously make requests to the server.



---



### **Documentation Changes Required** (Yes/No)

No



---

### **Logging Added/Updated** (Yes/No)

NA



--- 



### **Telemetry Added/Updated** (Yes/No) 

NA



---



### **Rollback Scenario and Process** (Yes/No)

NA



---



### **Dependency Impact Assessed and Regression Tested** (Yes/No)

NA
