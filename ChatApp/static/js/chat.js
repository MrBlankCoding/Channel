// Constants and DOM elements
const TYPING_TIMEOUT = 1000;
const messages = document.getElementById("messages");
const messageInput = document.getElementById("message");
const imageUpload = document.getElementById('image-upload');
const leaveRoomButton = document.getElementById("leave-room-btn");
const username = document.getElementById("username").value;

// State variables
let replyingTo = null;
let isUserListVisible = false;
let typingTimeout;
let currentUser = null;
let typingUsers = new Set();

// Socket connection
const socketio = io();

// Helper functions
const createTypingIndicator = () => {
  const typingIndicator = document.createElement("div");
  typingIndicator.className = "typing-indicator";
  typingIndicator.style.display = "none";
  messages.parentNode.insertBefore(typingIndicator, messages.nextSibling);
  return typingIndicator;
};

const typingIndicator = createTypingIndicator();

const createMessageElement = (name, msg, image, messageId, replyTo) => {
  const isCurrentUser = name === currentUser;
  
  const element = document.createElement("div");
  element.className = `message flex ${isCurrentUser ? 'justify-end' : 'justify-start'}`;

  const messageBubble = `
    <div class="group relative p-3 rounded-2xl shadow-sm max-w-[85%] md:max-w-[70%] hover:shadow-md transition-shadow duration-200
      ${isCurrentUser ? 'bg-indigo-600 text-white' : 'bg-gray-100 text-gray-900'}" 
      data-message-id="${messageId}">
      
      <!-- Message Content -->
      <div class="message-content">${msg || "Sent an image"}</div>

      <!-- Reply Information -->
      ${replyTo ? `
        <div class="reply-info mt-2 text-sm ${isCurrentUser ? 'text-white/75' : 'text-gray-500'} pl-3 border-l-2 border-current" data-reply-to="${replyTo.id}">
          Replying to: <span class="replied-message">${replyTo.message}</span>
        </div>
      ` : ''}

      <!-- Image -->
      ${image ? `
        <img src="${image}" alt="Uploaded image" class="mt-2 max-w-full rounded-lg">
      ` : ''}

      <!-- Hover Actions Menu -->
      <div class="opacity-0 group-hover:opacity-100 absolute -top-10 ${isCurrentUser ? 'right-0' : 'left-0'} 
           flex items-center space-x-1 bg-white rounded-lg shadow-lg px-2 py-1.5 transition-all duration-200 z-10">
        <!-- Reaction Button -->
        <button class="hover:bg-gray-100 p-1.5 rounded transition-colors duration-150" title="Add reaction">
          <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 text-gray-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.828 14.828a4 4 0 01-5.656 0M9 10h.01M15 10h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        </button>

        <!-- Reply Button -->
        <button class="hover:bg-gray-100 p-1.5 rounded transition-colors duration-150" title="Reply">
          <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 text-gray-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 10h10a8 8 0 018 8v2M3 10l6 6m-6-6l6-6" />
          </svg>
        </button>

        ${isCurrentUser ? `
          <!-- Edit Button (only for current user's messages) -->
          <button class="hover:bg-gray-100 p-1.5 rounded transition-colors duration-150" title="Edit">
            <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 text-gray-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
            </svg>
          </button>

          <!-- Delete Button (only for current user's messages) -->
          <button class="hover:bg-gray-100 p-1.5 rounded transition-colors duration-150" title="Delete">
            <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4 text-red-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
            </svg>
          </button>
        ` : ''}
      </div>

      <!-- Reactions Container -->
      <div class="message-reactions flex space-x-2 mt-2"></div>
      
      <!-- Reaction Menu -->
      <div class="reaction-menu hidden flex space-x-2 bg-gray-100 rounded-lg p-2 shadow-lg">
        <button class="emoji-reaction" data-emoji="👍">👍</button>
        <button class="emoji-reaction" data-emoji="❤️">❤️</button>
        <button class="emoji-reaction" data-emoji="😂">😂</button>
        <button class="emoji-reaction" data-emoji="😮">😮</button>
        <button class="emoji-reaction" data-emoji="😢">😢</button>
      </div>
    </div>
  `;

  element.innerHTML = messageBubble;

  // Add event listeners
  const messageElement = element.querySelector('[data-message-id]');
  
  // Reaction button listener
  const reactionBtn = messageElement.querySelector('button[title="Add reaction"]');
  if (reactionBtn) {
    reactionBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      const reactionMenu = messageElement.querySelector('.reaction-menu');
      reactionMenu.classList.toggle('hidden');
    });
  }

  // Reply button listener
  const replyBtn = messageElement.querySelector('button[title="Reply"]');
  if (replyBtn) {
    replyBtn.addEventListener('click', () => {
      startReply(messageId, msg);
    });
  }

  // Edit button listener
  const editBtn = messageElement.querySelector('button[title="Edit"]');
  if (editBtn) {
    editBtn.addEventListener('click', () => {
      editMessage(messageId);
    });
  }

  // Delete button listener
  const deleteBtn = messageElement.querySelector('button[title="Delete"]');
  if (deleteBtn) {
    deleteBtn.addEventListener('click', () => {
      deleteMessage(messageId);
    });
  }

  // Emoji reaction listener
  const emojiButtons = messageElement.querySelectorAll('.emoji-reaction');
  const reactionsContainer = messageElement.querySelector('.message-reactions');
  
  emojiButtons.forEach(button => {
    button.addEventListener('click', () => {
      const emoji = button.getAttribute('data-emoji');
      handleReaction(emoji, reactionsContainer); // Use the new handleReaction function
      messageElement.querySelector('.reaction-menu').classList.add('hidden');
    });
  });

  return element;
};

const createReplyContent = (replyTo) => `
  <div class="reply-info text-sm text-gray-500 italic" data-reply-to="${replyTo.id}">
    Replying to: <span class="replied-message">${replyTo.message}</span>
  </div>
`;

const createMessageActions = (isCurrentUser, messageId, msg) => 
  isCurrentUser 
    ? `
      <div class="message-actions">
        <button class="edit-btn">Edit</button>
        <button class="delete-btn">Delete</button>
      </div>
    ` 
    : `
      <div class="message-actions">
        <button class="reply-btn">Reply</button>
      </div>
    `;

    const addMessageToDOM = (element) => {
      // Create a container for the message if it doesn't exist
      let messageContainer = messages.querySelector('.flex.flex-col');
      if (!messageContainer) {
        messageContainer = document.createElement('div');
        messageContainer.className = 'flex flex-col space-y-4 p-4';
        messages.appendChild(messageContainer);
      }
      
      // Append the message to the container
      messageContainer.appendChild(element);
      messages.scrollTop = messages.scrollHeight;
      
      // Add event listeners for reactions and message actions
      const reactionButton = element.querySelector('.reaction-button');
      const reactionMenu = element.querySelector('.reaction-menu');
      
      if (reactionButton && reactionMenu) {
        reactionButton.addEventListener('click', (e) => {
          e.stopPropagation();
          reactionMenu.classList.toggle('hidden');
        });
      }
      
      // Add event listeners for edit and delete buttons
      if (element.querySelector('.edit-btn')) {
        const editBtn = element.querySelector('.edit-btn');
        editBtn.addEventListener('click', () => editMessage(element.getAttribute('data-message-id')));
      }
      
      if (element.querySelector('.delete-btn')) {
        const deleteBtn = element.querySelector('.delete-btn');
        deleteBtn.addEventListener('click', () => deleteMessage(element.getAttribute('data-message-id')));
      }
    };

const scrollToMessage = (messageId) => {
  const targetMessage = document.querySelector(`[data-message-id="${messageId}"]`);
  if (targetMessage) {
    targetMessage.scrollIntoView({ behavior: 'smooth', block: 'center' });
    targetMessage.style.backgroundColor = 'rgba(74, 144, 226, 0.1)';
    setTimeout(() => {
      targetMessage.style.backgroundColor = '';
    }, 2000);
  }
};

const startReply = (messageId, message) => {
  replyingTo = { id: messageId, message: message };
  messageInput.placeholder = `Replying to: ${message}`;
  messageInput.classList.add('replying');
  messageInput.focus();
};

const cancelReply = () => {
  replyingTo = null;
  messageInput.placeholder = "Type a message...";
  messageInput.classList.remove('replying');
};

const addReaction = (messageId, emoji) => {
  socketio.emit('add_reaction', { messageId, emoji });
};

socketio.on('update_reactions', (data) => {
  updateReactions(data.messageId, data.reactions);
});

const editMessage = (messageId) => {
  const messageElement = document.querySelector(`[data-message-id="${messageId}"]`);
  const messageContent = messageElement.querySelector('.message-content');
  const currentText = messageContent.textContent;
  const isCurrentUser = messageElement.classList.contains('bg-indigo-600');

  const input = document.createElement('input');
  input.type = 'text';
  input.value = currentText;
  // Update input styling to match message bubble colors
  input.className = `rounded-md p-1 w-full ${
    isCurrentUser 
      ? 'bg-indigo-700 text-white placeholder-indigo-300 border border-indigo-400' 
      : 'bg-white text-gray-900 border border-gray-300'
  }`;
  
  // Replace the content with the input field for editing
  messageContent.replaceWith(input);
  input.focus();

  // Handle the "Enter" key press or blur event to finish editing
  const handleEdit = (event) => {
    if (event.key === 'Enter' || event.type === 'blur') {
      const newText = input.value.trim();
      if (newText !== '' && newText !== currentText) {
        socketio.emit('edit_message', { messageId, newText });
      }
      finishEdit(newText, isCurrentUser);
    } else if (event.key === 'Escape') {
      finishEdit(currentText, isCurrentUser); // If escape, revert the message
    }
  };

  const finishEdit = (newText, isCurrentUser) => {
    input.removeEventListener('keyup', handleEdit);
    input.removeEventListener('blur', handleEdit);

    // Create a new span element with the updated message text
    const newMessageContent = document.createElement('div');
    newMessageContent.className = `message-content ${isCurrentUser ? 'text-white' : 'text-gray-900'}`;
    newMessageContent.textContent = newText;
    
    // Replace the input field with the updated message content
    input.replaceWith(newMessageContent);
  };

  input.addEventListener('keyup', handleEdit);
  input.addEventListener('blur', handleEdit);
};

const updateTypingIndicator = () => {
  const typingArray = Array.from(typingUsers);
  let typingText = '';

  if (typingArray.length === 1) {
    typingText = `${typingArray[0]} is typing...`;
  } else if (typingArray.length === 2) {
    typingText = `${typingArray[0]} and ${typingArray[1]} are typing...`;
  } else if (typingArray.length > 2) {
    typingText = `${typingArray[0]}, ${typingArray[1]}, and ${typingArray.length - 2} more are typing...`;
  }

  typingIndicator.textContent = typingText;
  typingIndicator.style.display = typingArray.length > 0 ? "block" : "none";
};

const deleteMessage = (messageId) => {
    if (confirm('Are you sure you want to delete this message?')) {
      socketio.emit('delete_message', { messageId });
    }
  };

const sendMessage = () => {
  const message = messageInput.value.trim();
  if (message === "") return;
  
  const messageData = { 
    data: message,
    replyTo: replyingTo
  };
  socketio.emit("message", messageData);
  // Don't clear the input here, we'll do it after confirmation
};

const leaveRoom = () => {
  const homeUrl = leaveRoomButton.getAttribute("data-home-url");
  window.location.href = homeUrl;
};
socketio.on("message_rejected", (data) => {
  alert(`Your message was not sent: ${data.reason}`);
  // You might want to keep the message in the input field so the user can modify it
});

// Event listeners
messageInput.addEventListener("keyup", (event) => {
  if (event.key === "Enter") {
    sendMessage();
  } else {
    socketio.emit("typing", { isTyping: true });
    clearTimeout(typingTimeout);
    typingTimeout = setTimeout(() => {
      socketio.emit("typing", { isTyping: false });
    }, TYPING_TIMEOUT);
  }
});

imageUpload.addEventListener('change', (event) => {
  const file = event.target.files[0];
  if (file) {
    const reader = new FileReader();
    reader.onload = (e) => {
      socketio.emit("message", { data: "Sent an image", image: e.target.result });
    };
    reader.readAsDataURL(file);
  }
});

const handleReaction = (emoji, reactionsContainer) => {
  // Check if the reaction already exists
  const existingReaction = reactionsContainer.querySelector(`span[data-emoji="${emoji}"]`);
  
  if (existingReaction) {
    // Update the count of the existing reaction
    let count = parseInt(existingReaction.getAttribute('data-count'));
    existingReaction.setAttribute('data-count', ++count);
    existingReaction.textContent = `${emoji} ${count}`;
  } else {
    // Add a new reaction
    const newReaction = document.createElement('span');
    newReaction.className = 'reaction';
    newReaction.setAttribute('data-emoji', emoji);
    newReaction.setAttribute('data-count', 1);
    newReaction.textContent = `${emoji} 1`;
    reactionsContainer.appendChild(newReaction);
  }
};

leaveRoomButton.addEventListener("click", leaveRoom);

socketio.on("message", (data) => {
  const messageElement = createMessageElement(data.name, data.message, data.image, data.id, data.replyTo, data.reactions);
  addMessageToDOM(messageElement);

  const replyInfo = messageElement.querySelector('.reply-info');
  if (replyInfo) {
    replyInfo.addEventListener('click', () => scrollToMessage(replyInfo.getAttribute('data-reply-to')));
  }

  if (data.name === currentUser) {
    // Clear the input field only when the message is successfully sent
    messageInput.value = "";
    cancelReply();

    const editBtn = messageElement.querySelector('.edit-btn');
    const deleteBtn = messageElement.querySelector('.delete-btn');
    editBtn.addEventListener('click', () => editMessage(data.id));
    deleteBtn.addEventListener('click', () => deleteMessage(data.id));
  } else {
    const replyBtn = messageElement.querySelector('.reply-btn');
    replyBtn.addEventListener('click', () => startReply(data.id, data.message));
  }
});

socketio.on("chat_history", (data) => {
  messages.innerHTML = '<div class="flex flex-col space-y-4 p-4"></div>';
  const messageContainer = messages.querySelector('.flex.flex-col');
  
  data.messages.forEach((message) => {
    const messageElement = createMessageElement(
      message.name, 
      message.message, 
      message.image, 
      message.id, 
      message.replyTo, 
      message.reactions
    );
    messageContainer.appendChild(messageElement);
  });
  
  messages.scrollTop = messages.scrollHeight;
});

socketio.on("edit_message", (data) => {
  const messageElement = document.querySelector(`[data-message-id="${data.messageId}"]`);
  if (messageElement) {
    const messageContent = messageElement.querySelector('.message-content');
    const isCurrentUser = messageElement.classList.contains('bg-indigo-600');
    messageContent.className = `message-content ${isCurrentUser ? 'text-white' : 'text-gray-900'}`;
    messageContent.textContent = data.newText;
  }
});
  
  // Listen for the "delete_message" event from the server
  socketio.on("delete_message", (data) => {
    const messageElement = document.querySelector(`[data-message-id="${data.messageId}"]`);
    if (messageElement) {
      messageElement.remove(); // Remove the message from the DOM
    }
  });

socketio.on("typing", (data) => {
  if (data.isTyping) {
    typingUsers.add(data.name);
  } else {
    typingUsers.delete(data.name);
  }
  updateTypingIndicator();
});

socketio.on("connect", () => {
  console.log("Connected to server");
  currentUser = username;
});

socketio.on("disconnect", () => {
  console.log("Disconnected from server");
});

// Add click event listener for toggling user list
document.querySelector('.user-toggle-btn').addEventListener('click', () => {
  const userList = document.getElementById('user-list');
  const userCountLabel = document.getElementById('user-count-label');
  
  // Toggle the visibility of the user list
  if (isUserListVisible) {
    // Hide user list and show the user count
    userList.classList.add('hidden');
    userCountLabel.classList.remove('hidden');
  } else {
    // Show user list and hide the user count
    userList.classList.remove('hidden');
    userCountLabel.classList.add('hidden');
  }
  
  // Update the toggle state
  isUserListVisible = !isUserListVisible;
});

// Your existing socket.io code for updating the user list
socketio.on("update_users", (data) => {
  const userList = document.getElementById("user-list");
  
  // Clear the current user list while keeping the label if screen size is md or larger
  userList.innerHTML = `
    <span class="user-list-label text-white font-semibold hidden md:inline">Users in room:</span>
  `;
  
  data.users.forEach(user => {
    // Create a container div for each user badge
    const userBadge = document.createElement("div");
    userBadge.className = "user-badge flex items-center gap-1.5 bg-white px-3 py-1 rounded-full shadow-sm group hover:bg-gray-100 transition";
    
    // Add the user's name (truncated if necessary)
    const userNameSpan = document.createElement("span");
    userNameSpan.className = "truncate max-w-[100px] text-gray-800";
    userNameSpan.textContent = user.username;

    // Add the online/offline status indicator
    const statusIndicator = document.createElement("span");
    if (user.online) {
      statusIndicator.innerHTML = '<span class="text-green-400">🟢</span>';
    } else {
      statusIndicator.innerHTML = '<span class="text-gray-400">⚫</span>';
    }

    // Append the friend star if the user is a friend
    if (user.isFriend) {
      const friendStar = document.createElement("span");
      friendStar.className = "friend-star text-yellow-300";
      friendStar.textContent = '★';
      userBadge.appendChild(friendStar);
    }

    // Append elements to the user badge
    userBadge.appendChild(userNameSpan);
    userBadge.appendChild(statusIndicator);

    // Add the user badge to the user list
    userList.appendChild(userBadge);
  });
});
